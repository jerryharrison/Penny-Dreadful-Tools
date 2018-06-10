from typing import List, Optional, Sequence, Union

from decksite.data import deck, query
from decksite.database import db
from shared import dtutil, guarantee
from shared.container import Container
from shared.database import sqlescape
from shared.pd_exception import AlreadyExistsException
from shared_web import logger


class Person(Container):
    __decks = None
    @property
    def decks(self) -> List[deck.Deck]:
        if self.__decks is None:
            self.__decks = deck.load_decks(f'd.person_id = {self.id}', season_id=self.season_id)
        return self.__decks

def load_person(person: Union[int, str], season_id: Optional[int] = None) -> Person:
    try:
        person_id = int(person)
        username = "'{person}'".format(person=person)
    except ValueError:
        person_id = 0
        username = sqlescape(person)
    return guarantee.exactly_one(load_people('p.id = {person_id} OR p.mtgo_username = {username} OR p.discord_id = {person_id}'.format(person_id=person_id, username=username), season_id=season_id))

def load_people(where: str = '1 = 1',
                order_by: str = '`all_num_decks` DESC, name',
                season_id: Optional[int] = None) -> Sequence[Person]:
    sql = """
        SELECT
            p.id,
            {person_query} AS name,
            p.mtgo_username,
            p.tappedout_username,
            p.mtggoldfish_username,
            p.discord_id,
            p.elo,
            {all_select},
            SUM(DISTINCT CASE WHEN d.competition_id IS NOT NULL AND {season_query} THEN 1 ELSE 0 END) AS `all_num_competitions`
        FROM
            person AS p
        LEFT JOIN
            deck AS d ON p.id = d.person_id
        {season_join}
        {nwdl_join}
        WHERE
            ({where})
        GROUP BY
            p.id
        ORDER BY
            {order_by}
    """.format(person_query=query.person_query(), all_select=deck.nwdl_select('all_', query.season_query(season_id)), nwdl_join=deck.nwdl_join(), season_join=query.season_join(), where=where, season_query=query.season_query(season_id), order_by=order_by)

    people = [Person(r) for r in db().execute(sql)]
    for p in people:
        p.season_id = season_id

    if len(people) > 0:
        set_achievements(people, season_id)
        set_head_to_head(people, season_id)
    return people

def set_achievements(people: List[Person], season_id: int = None) -> None:
    people_by_id = {person.id: person for person in people}
    sql = """
        SELECT
            p.id,
            COUNT(DISTINCT CASE WHEN ct.name = 'Gatherling' THEN d.id ELSE NULL END) AS tournament_entries,
            COUNT(DISTINCT CASE WHEN d.finish = 1 AND ct.name = 'Gatherling' THEN d.id ELSE NULL END) AS tournament_wins,
            COUNT(DISTINCT CASE WHEN ct.name = 'League' THEN d.id ELSE NULL END) AS league_entries,
            SUM(
                CASE WHEN d.id IN
                    (
                        SELECT
                            d.id
                        FROM
                            deck AS d
                        {competition_join}
                        LEFT JOIN
                            deck_match AS dm ON dm.deck_id = d.id
                        LEFT JOIN
                            deck_match AS odm ON odm.match_id = dm.match_id AND odm.deck_id <> d.id
                        WHERE
                            ct.name = 'League'
                        GROUP BY
                            d.id
                        HAVING
                            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) >= 5
                        AND
                            SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) = 0
                    )
                THEN 1 ELSE 0 END
            ) AS perfect_runs,
            SUM(
                CASE WHEN d.id IN
                    (
                        SELECT
                            -- MAX here is just to fool MySQL to give us the id of the deck that crushed the perfect run from an aggregate function. There is only one value to MAX.
                            MAX(CASE WHEN dm.games < odm.games AND dm.match_id IN (SELECT MAX(match_id) FROM deck_match WHERE deck_id = d.id) THEN odm.deck_id ELSE NULL END) AS deck_id
                        FROM
                            deck AS d
                        INNER JOIN
                            deck_match AS dm
                        ON
                            dm.deck_id = d.id
                        INNER JOIN
                            deck_match AS odm
                        ON
                            dm.match_id = odm.match_id AND odm.deck_id <> d.id
                        WHERE
                            d.competition_id IN ({competition_ids_by_type_select})
                        GROUP BY d.id
                        HAVING
                            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) >=4
                        AND
                            SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) = 1
                        AND
                            SUM(CASE WHEN dm.games < odm.games AND dm.match_id IN (SELECT MAX(match_id) FROM deck_match WHERE deck_id = d.id) THEN 1 ELSE 0 END) = 1
                    )
                THEN 1 ELSE 0 END
            ) AS perfect_run_crushes
        FROM
            person AS p
        LEFT JOIN
            deck AS d ON d.person_id = p.id
        {season_join}
        {competition_join}
        WHERE
            p.id IN ({ids}) AND ({season_query})
        GROUP BY
            p.id
    """.format(competition_join=query.competition_join(), competition_ids_by_type_select=query.competition_ids_by_type_select('League'), ids=', '.join(str(k) for k in people_by_id.keys()), season_join=query.season_join(), season_query=query.season_query(season_id))
    results = [Container(r) for r in db().execute(sql)]
    for result in results:
        people_by_id[result['id']].update(result)
        people_by_id[result['id']].achievements = len([k for k, v in result.items() if k != 'id' and v > 0])

def set_head_to_head(people: List[Person], season_id: int = None) -> None:
    people_by_id = {person.id: person for person in people}
    sql = """
        SELECT
            p.id,
            COUNT(p.id) AS num_matches,
            LOWER(opp.mtgo_username) AS opp_mtgo_username,
            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) AS losses,
            SUM(CASE WHEN dm.games = odm.games THEN 1 ELSE 0 END) AS draws,
            IFNULL(ROUND((SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN dm.games <> IFNULL(odm.games, 0) THEN 1 ELSE 0 END), 0)) * 100, 1), '') AS win_percent
        FROM
            person AS p
        INNER JOIN
            deck AS d ON p.id = d.person_id
        INNER JOIN
            deck_match AS dm ON dm.deck_id = d.id
        INNER JOIN
            deck_match AS odm ON dm.match_id = odm.match_id AND dm.deck_id <> IFNULL(odm.deck_id, 0)
        INNER JOIN
            deck AS od ON odm.deck_id = od.id
        INNER JOIN
            person AS opp ON od.person_id = opp.id
        {season_join}
        WHERE
            p.id IN ({ids}) AND ({season_query})
        GROUP BY
            p.id, opp.id
        ORDER BY
            p.id,
            num_matches DESC,
            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) - SUM(CASE WHEN dm.games < odm.games THEN 1 ELSE 0 END) DESC,
            win_percent DESC,
            SUM(CASE WHEN dm.games > odm.games THEN 1 ELSE 0 END) DESC,
            opp_mtgo_username
    """.format(ids=', '.join(str(k) for k in people_by_id.keys()), season_join=query.season_join(), season_query=query.season_query(season_id))
    results = [Container(r) for r in db().execute(sql)]
    for result in results:
        people_by_id[result.id].head_to_head = people_by_id[result.id].get('head_to_head', []) + [result]
    for person in people:
        if person.get('head_to_head') is None:
            person.head_to_head = []

def associate(d, discord_id):
    person = guarantee.exactly_one(load_people('d.id = {deck_id}'.format(deck_id=sqlescape(d.id))))
    sql = 'UPDATE person SET discord_id = %s WHERE id = %s'
    return db().execute(sql, [discord_id, person.id])

def is_allowed_to_retire(deck_id, discord_id):
    if not deck_id:
        return False
    if not discord_id:
        return True
    person = load_person_by_discord_id(discord_id)
    if person is None:
        return True
    return any(int(deck_id) == deck.id for deck in person.decks)

def load_person_by_discord_id(discord_id: Optional[int]) -> Optional[Person]:
    if discord_id is None:
        return None
    return guarantee.at_most_one(load_people('p.discord_id = {discord_id}'.format(discord_id=sqlescape(discord_id))))

def load_person_by_tappedout_name(username: str) -> Optional[Person]:
    return guarantee.at_most_one(load_people('p.tappedout_username = {username}'.format(username=sqlescape(username))))

def load_person_by_mtggoldfish_name(username: str) -> Optional[Person]:
    return guarantee.at_most_one(load_people('p.mtggoldfish_username = {username}'.format(username=sqlescape(username))))

def get_or_insert_person_id(mtgo_username: Optional[str], tappedout_username: Optional[str], mtggoldfish_username: Optional[str]) -> int:
    sql = 'SELECT id FROM person WHERE LOWER(mtgo_username) = LOWER(%s) OR LOWER(tappedout_username) = LOWER(%s) OR LOWER(mtggoldfish_username) = LOWER(%s)'
    person_id = db().value(sql, [mtgo_username, tappedout_username, mtggoldfish_username])
    if person_id:
        return person_id
    sql = 'INSERT INTO person (mtgo_username, tappedout_username, mtggoldfish_username) VALUES (%s, %s, %s)'
    return db().insert(sql, [mtgo_username, tappedout_username, mtggoldfish_username])

def load_notes() -> List[Container]:
    sql = """
        SELECT
            pn.created_date,
            pn.creator_id,
            {creator_query} AS creator,
            pn.subject_id,
            {subject_query} AS subject,
            note
        FROM
            person_note AS pn
        INNER JOIN
            person AS c ON pn.creator_id = c.id
        INNER JOIN
            person AS s ON pn.subject_id = s.id
        ORDER BY
            s.id,
            pn.created_date DESC
    """.format(creator_query=query.person_query('c'), subject_query=query.person_query('s'))
    notes = [Container(r) for r in db().execute(sql)]
    for n in notes:
        n.created_date = dtutil.ts2dt(n.created_date)
    return notes

def add_note(creator_id: int, subject_id: int, note: str) -> None:
    sql = 'INSERT INTO person_note (created_date, creator_id, subject_id, note) VALUES (UNIX_TIMESTAMP(NOW()), %s, %s, %s)'
    db().execute(sql, [creator_id, subject_id, note])

def link_discord(mtgo_username: str, discord_id: int) -> Person:
    person_id = deck.get_or_insert_person_id(mtgo_username, None, None)
    p = load_person(person_id)
    if p.discord_id is not None:
        raise AlreadyExistsException('Player with mtgo username {mtgo_username} already has discord id {old_discord_id}, cannot add {new_discord_id}'.format(mtgo_username=mtgo_username, old_discord_id=p.discord_id, new_discord_id=discord_id))
    sql = 'UPDATE person SET discord_id = %s WHERE id = %s'
    db().execute(sql, [discord_id, p.id])
    return p

def is_banned(mtgo_username):
    return db().value('SELECT banned FROM person WHERE mtgo_username = %s', [mtgo_username]) == 1

def squash(p1id: int, p2id: int, col1: str, col2: str) -> None:
    logger.warning('Squashing {p1id} and {p2id} on {col1} and {col2}'.format(p1id=p1id, p2id=p2id, col1=col1, col2=col2))
    db().begin()
    new_value = db().value('SELECT {col2} FROM person WHERE id = %s'.format(col2=col2), [p2id])
    db().execute('UPDATE deck SET person_id = %s WHERE person_id = %s', [p1id, p2id])
    db().execute('DELETE FROM person WHERE id = %s', [p2id])
    db().execute('UPDATE person SET {col2} = %s WHERE id = %s'.format(col2=col2), [new_value, p1id])
    db().commit()
