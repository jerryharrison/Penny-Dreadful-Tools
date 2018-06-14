import hashlib
import json
import time
from typing import Dict, List, Optional, Set

from decksite import deck_name
from decksite.data import query
from decksite.data.top import Top
from decksite.database import db
from magic import legality, mana, oracle, rotation
from magic.models.deck import Deck
from shared import dtutil, guarantee, redis
from shared.container import Container
from shared.database import sqlescape
from shared.pd_exception import InvalidDataException


def load_deck(deck_id: int) -> Deck:
    return guarantee.exactly_one(load_decks('d.id = {deck_id}'.format(deck_id=sqlescape(deck_id))))

def load_season(season_id: int = None, league_only: bool = False) -> Container:
    season = Container()
    where = 'TRUE'
    if league_only:
        where = 'd.competition_id IN ({competition_ids_by_type_select})'.format(competition_ids_by_type_select=query.competition_ids_by_type_select('League'))
    season.decks = load_decks(where, season_id=season_id)
    season.number = season_id
    return season

# pylint: disable=attribute-defined-outside-init
def load_decks(where: str = '1 = 1',
               order_by: Optional[str] = None,
               limit: str = '',
               season_id: Optional[int] = None
              ) -> List[Deck]:
    if redis.REDIS is None:
        return load_decks_heavy(where, order_by, limit, season_id)
    if order_by is None:
        order_by = 'active_date DESC, d.finish IS NULL, d.finish'
    sql = """
        SELECT
            d.id,
            d.finish,
            IFNULL(MAX(m.date), d.created_date) AS active_date
        FROM
            deck AS d
        LEFT JOIN
            deck_match AS dm ON d.id = dm.deck_id
        LEFT JOIN
            `match` AS m ON dm.match_id = m.id
        LEFT JOIN
            deck_match AS odm ON odm.deck_id <> d.id AND dm.match_id = odm.match_id
        """
    if 'p.' in where or 'p.' in order_by:
        sql += """
        LEFT JOIN
            person AS p ON d.person_id = p.id
        """
    if 's.' in where or 's.' in order_by:
        sql += """
        LEFT JOIN
            source AS s ON d.source_id = s.id
        """
    if 'a.' in where or 'a.' in order_by:
        sql += """
        LEFT JOIN
            archetype AS a ON d.archetype_id = a.id
        """
    sql += """
        {competition_join}
        """
    if 'cache.' in where or 'cache.' in order_by:
        sql += """
        LEFT JOIN
            deck_cache AS cache ON d.id = cache.deck_id
        """
    sql += """
        {season_join}
        WHERE ({where}) AND ({season_query})
        GROUP BY
            d.id,
            season.id -- In theory this is not necessary as all decks are in a single season and we join on the date but MySQL cannot work that out so give it the hint it needs.
        ORDER BY
            {order_by}
        {limit}
    """
    sql = sql.format(person_query=query.person_query(), competition_join=query.competition_join(), where=where, order_by=order_by, limit=limit, season_query=query.season_query(season_id), season_join=query.season_join())
    db().execute('SET group_concat_max_len=100000')
    rows = db().execute(sql)
    decks = []
    heavy = []
    for row in rows:
        d = redis.get_container('decksite:deck:{id}'.format(id=row['id']))
        if d is None or d.name is None:
            heavy.append(row['id'])
            # decks.append(guarantee.exactly_one(load_decks_heavy('d.id = {id}'.format(id=row['id']))))
        else:
            decks.append(deserialize_deck(d))
    if heavy:
        # This currently messes up the order.
        where = 'd.id IN ({deck_ids})'.format(deck_ids=', '.join(map(sqlescape, map(str, heavy))))
        decks.extend(load_decks_heavy(where))
    return decks

def deserialize_deck(sdeck: Container) -> Deck:
    deck = Deck(sdeck)
    deck.active_date = dtutil.ts2dt(deck.active_date)
    deck.created_date = dtutil.ts2dt(deck.created_date)
    deck.updated_date = dtutil.ts2dt(deck.updated_date)
    if deck.competition_end_date is not None:
        deck.competition_end_date = dtutil.ts2dt(deck.competition_end_date)
    deck.wins = int(deck.wins)
    deck.losses = int(deck.losses)
    deck.draws = int(deck.draws)
    if deck.get('omw') is not None:
        deck.omw = float(deck.omw)
    cards_by_name = oracle.cards_by_name()
    for entry in deck.maindeck:
        entry['card'] = cards_by_name[entry['card']['name']]
    for entry in deck.sideboard:
        entry['card'] = cards_by_name[entry['card']['name']]
    return deck

def load_decks_heavy(where: str = '1 = 1',
                     order_by: Optional[str] = None,
                     limit: str = '',
                     season_id: Optional[int] = None
                    ) -> List[Deck]:
    if order_by is None:
        order_by = 'active_date DESC, d.finish IS NULL, d.finish'
    sql = """
        SELECT
            d.id,
            d.name AS original_name,
            d.created_date,
            d.updated_date,
            SUM(CASE WHEN dm.games > IFNULL(odm.games, 0) THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN dm.games = odm.games THEN 1 ELSE 0 END) AS draws,
            d.finish,
            d.archetype_id,
            d.url AS source_url,
            d.competition_id,
            c.name AS competition_name,
            c.end_date AS competition_end_date,
            c.top_n AS competition_top_n,
            ct.name AS competition_type_name,
            d.identifier,
            {person_query} AS person,
            p.id AS person_id,
            p.banned,
            p.discord_id,
            d.decklist_hash,
            d.retired,
            s.name AS source_name,
            IFNULL(a.name, '') AS archetype_name,
            cache.normalized_name AS name,
            cache.colors,
            cache.colored_symbols,
            cache.legal_formats,
            season.id AS season_id,
            IFNULL(MAX(m.date), d.created_date) AS active_date
        FROM
            deck AS d
        LEFT JOIN
            person AS p ON d.person_id = p.id
        LEFT JOIN
            source AS s ON d.source_id = s.id
        LEFT JOIN
            archetype AS a ON d.archetype_id = a.id
        {competition_join}
        LEFT JOIN
            deck_cache AS cache ON d.id = cache.deck_id
        LEFT JOIN
            deck_match AS dm ON d.id = dm.deck_id
        LEFT JOIN
            `match` AS m ON dm.match_id = m.id
        LEFT JOIN
            deck_match AS odm ON odm.deck_id <> d.id AND dm.match_id = odm.match_id
        {season_join}
        WHERE ({where}) AND ({season_query})
        GROUP BY
            d.id,
            season.id -- In theory this is not necessary as all decks are in a single season and we join on the date but MySQL cannot work that out so give it the hint it needs.
        ORDER BY
            {order_by}
        {limit}
    """.format(person_query=query.person_query(), competition_join=query.competition_join(), where=where, order_by=order_by, limit=limit, season_query=query.season_query(season_id), season_join=query.season_join())
    db().execute('SET group_concat_max_len=100000')
    rows = db().execute(sql)
    decks = []
    for row in rows:
        d = Deck(row)
        d.maindeck = []
        d.sideboard = []
        d.competition_top_n = Top(d.competition_top_n or 0)
        d.colored_symbols = json.loads(d.colored_symbols or '[]')
        d.colors = json.loads(d.colors or '[]')
        d.legal_formats = set(json.loads(d.legal_formats or '[]'))
        d.active_date = dtutil.ts2dt(d.active_date)
        d.created_date = dtutil.ts2dt(d.created_date)
        d.updated_date = dtutil.ts2dt(d.updated_date)
        if d.competition_end_date:
            d.competition_end_date = dtutil.ts2dt(d.competition_end_date)
        d.can_draw = 'Divine Intervention' in [card.name for card in d.all_cards()]
        decks.append(d)
    load_cards(decks)
    load_competitive_stats(decks)
    for d in decks:
        expiry = 60 if d.is_in_current_run() else 3600
        redis.store('decksite:deck:{id}'.format(id=d.id), d, ex=expiry)
    return decks

# We ignore 'also' here which means if you are playing a deck where there are no other G or W cards than Kitchen Finks we will claim your deck is neither W nor G which is not true. But this should cover most cases.
# We also ignore split and aftermath cards so if you are genuinely using a color in a split card but have no other cards of that color we won't claim it as one of the deck's colors.
def set_colors(d: Deck) -> None:
    deck_colors: Set[str] = set()
    deck_colored_symbols: List[str] = []
    for c in [entry['card'] for entry in d.maindeck + d.sideboard]:
        for cost in c.get('mana_cost') or ():
            if c.layout == 'split' or c.layout == 'aftermath':
                continue # They might only be using one half so ignore it.
            card_symbols = mana.parse(cost)
            card_colors = mana.colors(card_symbols)
            deck_colors.update(card_colors['required'])
            card_colored_symbols = mana.colored_symbols(card_symbols)
            deck_colored_symbols += card_colored_symbols['required']
    d.colors = mana.order(deck_colors)
    d.colored_symbols = deck_colored_symbols

def set_legality(d: Deck) -> None:
    d.legal_formats = legality.legal_formats(d)

# Expects:
#
# {
#     'name': <string>,
#     'url': <string>,
#     'source': <string>,
#     'identifier': <string>,
#     'cards' {
#         'maindeck': {
#             '<canonical card name>': <int>,
#             …
#         },
#         'sideboard': {
#             '<canonical card name>': <int>,
#             …
#         }
#     }
# }
# Plus one of: mtgo_username OR tappedout_username OR mtggoldfish_username
# Optionally: created_date (unix timestamp, defaults to now), resource_uri, featured_card, score, thumbnail_url, small_thumbnail_url, wins, losses, draws, finish
#
# source + identifier must be unique for each decklist.
def add_deck(params) -> Deck:
    if not params.get('mtgo_username') and not params.get('tappedout_username') and not params.get('mtggoldfish_username'):
        raise InvalidDataException('Did not find a username in {params}'.format(params=params))
    person_id = get_or_insert_person_id(params.get('mtgo_username'), params.get('tappedout_username'), params.get('mtggoldfish_username'))
    deck_id = get_deck_id(params['source'], params['identifier'])
    if deck_id:
        add_cards(deck_id, params['cards'])
        d = load_deck(deck_id)
        prime_cache(d)
        return d
    created_date = params.get('created_date')
    if not created_date:
        created_date = time.time()
    archetype_id = get_archetype_id(params.get('archetype'))
    for result in ['wins', 'losses', 'draws']:
        if params.get('competition_id') and not params.get(result):
            params[result] = 0
    sql = """INSERT INTO deck (
        created_date,
        updated_date,
        person_id,
        source_id,
        url,
        identifier,
        name,
        competition_id,
        archetype_id,
        resource_uri,
        featured_card,
        score,
        thumbnail_url,
        small_thumbnail_url,
        finish,
        reviewed
    ) VALUES (
         IFNULL(%s, UNIX_TIMESTAMP()),  UNIX_TIMESTAMP(), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE
    )"""
    values = [
        created_date,
        person_id,
        get_source_id(params['source']),
        params['url'],
        params['identifier'],
        params['name'],
        params.get('competition_id'),
        archetype_id,
        params.get('resource_uri'),
        params.get('featured_card'),
        params.get('score'),
        params.get('thumbnail_url'),
        params.get('small_thumbnail_url'),
        params.get('finish')
    ]
    deck_id = db().insert(sql, values)
    add_cards(deck_id, params['cards'])
    d = load_deck(deck_id)
    prime_cache(d)
    return d

def prime_cache(d: Deck) -> None:
    set_colors(d)
    colors_s = json.dumps(d.colors)
    colored_symbols_s = json.dumps(d.colored_symbols)
    set_legality(d)
    legal_formats_s = json.dumps(list(d.legal_formats))
    normalized_name = deck_name.normalize(d)
    db().begin()
    db().execute('DELETE FROM deck_cache WHERE deck_id = %s', [d.id])
    db().execute('INSERT INTO deck_cache (deck_id, normalized_name, colors, colored_symbols, legal_formats) VALUES (%s, %s, %s, %s, %s)', [d.id, normalized_name, colors_s, colored_symbols_s, legal_formats_s])
    db().commit()

def add_cards(deck_id: int, cards) -> None:
    db().begin()
    deckhash = hashlib.sha1(repr(cards).encode('utf-8')).hexdigest()
    db().execute('UPDATE deck SET decklist_hash = %s WHERE id = %s', [deckhash, deck_id])
    db().execute('DELETE FROM deck_card WHERE deck_id = %s', [deck_id])
    for name, n in cards['maindeck'].items():
        insert_deck_card(deck_id, name, n, False)
    for name, n in cards['sideboard'].items():
        insert_deck_card(deck_id, name, n, True)
    db().commit()

def get_deck_id(source_name, identifier) -> Optional[int]:
    source_id = get_source_id(source_name)
    sql = 'SELECT id FROM deck WHERE source_id = %s AND identifier = %s'
    return db().value(sql, [source_id, identifier])

def insert_deck_card(deck_id: int, name: str, n, in_sideboard) -> None:
    name = oracle.valid_name(name)
    sql = 'INSERT INTO deck_card (deck_id, card, n, sideboard) VALUES (%s, %s, %s, %s)'
    db().execute(sql, [deck_id, name, n, in_sideboard])

def get_or_insert_person_id(mtgo_username: Optional[str], tappedout_username: Optional[str], mtggoldfish_username: Optional[str]) -> int:
    sql = 'SELECT id FROM person WHERE LOWER(mtgo_username) = LOWER(%s) OR LOWER(tappedout_username) = LOWER(%s) OR LOWER(mtggoldfish_username) = LOWER(%s)'
    person_id = db().value(sql, [mtgo_username, tappedout_username, mtggoldfish_username])
    if person_id:
        return person_id
    sql = 'INSERT INTO person (mtgo_username, tappedout_username, mtggoldfish_username) VALUES (%s, %s, %s)'
    return db().insert(sql, [mtgo_username, tappedout_username, mtggoldfish_username])

def get_source_id(source: str) -> int:
    sql = 'SELECT id FROM source WHERE name = %s'
    source_id = db().value(sql, [source])
    if not source_id:
        raise InvalidDataException('Unknown source: `{source}`'.format(source=source))
    return source_id

def get_archetype_id(archetype: str) -> Optional[int]:
    sql = 'SELECT id FROM archetype WHERE name = %s'
    return db().value(sql, [archetype])

def load_similar_decks(ds: List[Deck]) -> None:
    for d in ds:
        d.similar_decks = []

def all_card_names(ds: List[Deck]) -> Set[str]:
    basic_lands = ['Plains', 'Island', 'Swamp', 'Mountain', 'Forest']
    names = set()
    for d in ds:
        for c in d.maindeck:
            if c['name'] not in basic_lands and c['name']:
                names.add(c['name'])
    return names

# Dead simple for now, may get more sophisticated. 1 point for each differently named card shared in maindeck. Count irrelevant.
def similarity_score(a: Deck, b: Deck) -> float:
    score = 0
    for c in a.maindeck:
        if c in b.maindeck:
            score += 1
    return float(score) / float(max(len(a.maindeck), len(b.maindeck)))

def load_decks_by_cards(names: List[str]) -> List[Deck]:
    sql = """
        d.id IN (
            SELECT deck_id
            FROM deck_card
            WHERE card IN ({names})
            GROUP BY deck_id
            HAVING COUNT(DISTINCT card) = {n})
        """.format(n=len(names), names=', '.join(map(sqlescape, names)))
    return load_decks(sql)

def load_cards(decks: List[Deck]) -> None:
    if len(decks) == 0:
        return
    decks_by_id = {d.id: d for d in decks}
    cards = oracle.cards_by_name()
    sql = """
        SELECT deck_id, card, n, sideboard FROM deck_card WHERE deck_id IN ({deck_ids})
    """.format(deck_ids=', '.join(map(sqlescape, map(str, decks_by_id.keys()))))
    rs = db().execute(sql)
    for row in rs:
        location = 'sideboard' if row['sideboard'] else 'maindeck'
        name = row['card']
        d = decks_by_id[row['deck_id']]
        d[location] = d.get(location, [])
        d[location].append({'n': row['n'], 'name': name, 'card': cards[name]})

# It makes the main query about 5x faster to do this as a separate query (which is trivial and done only once for all decks).
def load_competitive_stats(decks: List[Deck]) -> None:
    if len(decks) == 0:
        return
    decks_by_id = {d.id: d for d in decks}
    if len(decks) < 1000:
        where = 'd.id IN ({deck_ids})'.format(deck_ids=', '.join(map(sqlescape, map(str, decks_by_id.keys()))))
    else:
        where = 'TRUE' # MySQL doesn't like to be asked to do IN queries for very long argument lists. Just load everything. (MariaDB doesn't care, interestingly.)
    sql = """
        SELECT
            d.id,
            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) AS opp_wins,
            SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) AS opp_losses,
            SUM(CASE WHEN dm.games = odm.games THEN 1 ELSE 0 END) AS opp_draws,
            ROUND(SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) / NULLIF((SUM(CASE WHEN dm.games <> odm.games THEN 1 ELSE 0 END)), 0), 2) * 100 AS omw,
            GROUP_CONCAT(m.elimination) AS elim
        FROM
            deck AS d
        INNER JOIN
            deck_match AS my_dm ON my_dm.deck_id = d.id
        LEFT JOIN
            deck_match AS my_odm ON my_odm.match_id = my_dm.match_id AND my_odm.deck_id <> d.id
        INNER JOIN
            deck AS od ON od.id = my_odm.deck_id
        INNER JOIN
            deck_match AS dm ON dm.deck_id = od.id
        LEFT JOIN
            deck_match AS odm ON odm.match_id = dm.match_id AND odm.deck_id <> dm.deck_id
        INNER JOIN
            `match` AS m ON m.id = dm.match_id
        WHERE
            {where}
        GROUP BY
            d.id
    """.format(where=where)
    rs = db().execute(sql)
    for row in rs:
        if decks_by_id.get(row['id']):
            decks_by_id[row['id']].opp_wins = row['opp_wins']
            decks_by_id[row['id']].opp_losses = row['opp_losses']
            decks_by_id[row['id']].omw = row['omw']
            decks_by_id[row['id']].elim = row['elim'] # This property is never used? and is always a bunch of zeroes?

def count_matches(deck_id: int, opponent_deck_id: int) -> Dict[int, int]:
    sql = 'SELECT deck_id, count(id) as count FROM deck_match WHERE deck_id in (%s, %s) group by deck_id'
    result = {int(deck_id): 0, int(opponent_deck_id): 0}
    for row in db().execute(sql, [deck_id, opponent_deck_id]):
        result[row['deck_id']] = row['count']
    return result

# Query Helpers for number of decks, wins, draws and losses.

def nwdl_select(prefix: str = '', additional_clause: str = 'TRUE') -> str:
    return """
        SUM(CASE WHEN {additional_clause} AND d.id IS NOT NULL THEN 1 ELSE 0 END) AS `{prefix}num_decks`,
        SUM(CASE WHEN {additional_clause} THEN wins ELSE 0 END) AS `{prefix}wins`,
        SUM(CASE WHEN {additional_clause} THEN losses ELSE 0 END) AS `{prefix}losses`,
        SUM(CASE WHEN {additional_clause} THEN draws ELSE 0 END) AS `{prefix}draws`,
        SUM(CASE WHEN {additional_clause} AND wins >= 5 AND losses = 0 AND d.source_id IN (SELECT id FROM source WHERE name = 'League') THEN 1 ELSE 0 END) AS {prefix}perfect_runs,
        SUM(CASE WHEN {additional_clause} AND dsum.finish = 1 THEN 1 ELSE 0 END) AS `{prefix}tournament_wins`,
        SUM(CASE WHEN {additional_clause} AND dsum.finish <= 8 THEN 1 ELSE 0 END) AS `{prefix}tournament_top8s`,
        IFNULL(ROUND((SUM(CASE WHEN {additional_clause} THEN wins ELSE 0 END) / NULLIF(SUM(CASE WHEN {additional_clause} THEN wins + losses ELSE 0 END), 0)) * 100, 1), '') AS `{prefix}win_percent`
    """.format(prefix=prefix, additional_clause=additional_clause)

def nwdl_all_select() -> str:
    return nwdl_select('all_')

def nwdl_season_select() -> str:
    return nwdl_select('season_', 'dsum.created_date >= {season_start}'.format(season_start=int(rotation.last_rotation().timestamp())))

def nwdl_week_select() -> str:
    return nwdl_select('week_', 'dsum.created_date >= UNIX_TIMESTAMP(NOW() - INTERVAL 1 WEEK)')

def nwdl_join() -> str:
    return """
        LEFT JOIN
            (
                SELECT
                    d.id,
                    d.created_date,
                    d.finish,
                    SUM(CASE WHEN dm.games > IFNULL(odm.games, 0) THEN 1 ELSE 0 END) AS wins, -- IFNULL so we still count byes as wins.
                    SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) AS losses,
                    SUM(CASE WHEN dm.games = odm.games THEN 1 ELSE 0 END) AS draws
                FROM
                    deck_match AS dm
                INNER JOIN
                    deck_match AS odm ON dm.match_id = odm.match_id AND dm.deck_id <> odm.deck_id
                INNER JOIN
                    deck AS d ON d.id = dm.deck_id
                GROUP BY
                    d.id
            ) AS dsum ON d.id = dsum.id
    """
