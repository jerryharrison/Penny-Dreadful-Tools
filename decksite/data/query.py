from typing import Optional

from shared.pd_exception import InvalidArgumentException


def person_query(table: str = 'p') -> str:
    return 'LOWER(IFNULL(IFNULL(IFNULL({table}.name, {table}.mtgo_username), {table}.mtggoldfish_username), {table}.tappedout_username))'.format(table=table)

def competition_ids_by_type_select(competition_type: str) -> str:
    return """
        SELECT
            id
        FROM
            competition
        WHERE
            competition_series_id IN
                (
                    SELECT
                        id
                    FROM
                        competition_series
                    WHERE
                        competition_type_id
                    IN ({competition_type_id})
                )
        """.format(competition_type_id=competition_type_id_select(competition_type))

def competition_type_id_select(competition_type: str) -> str:
    return """
        SELECT
            id
        FROM
            competition_type
        WHERE
            name = '{competition_type}'
    """.format(competition_type=competition_type)

def competition_join() -> str:
    return """
        LEFT JOIN
            competition AS c ON d.competition_id = c.id
        LEFT JOIN
            competition_series AS cs ON cs.id = c.competition_series_id
        LEFT JOIN
            competition_type AS ct ON ct.id = cs.competition_type_id
    """

def season_query(season_id: Optional[int]) -> str:
    if season_id is None or season_id == 'all':
        return 'TRUE'
    try:
        return 'season.id = {season_id}'.format(season_id=int(season_id))
    except ValueError:
        raise InvalidArgumentException('No season with id `{season_id}`'.format(season_id=season_id))

def season_join() -> str:
    return """
        LEFT JOIN
            ({season_table}) AS season ON season.start_date <= d.created_date AND (season.end_date IS NULL OR season.end_date > d.created_date)
    """.format(season_table=season_table())

def season_table() -> str:
    return """
        SELECT
            `start`.id,
            `start`.code,
            `start`.start_date AS start_date,
            `end`.start_date AS end_date
        FROM
            season AS `start`
        LEFT JOIN
            season AS `end` ON `end`.id = `start`.id + 1
    """
