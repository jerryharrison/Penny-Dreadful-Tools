from typing import List

import pytest

from decksite import deck_name
from shared.container import Container
from shared.pd_exception import InvalidDataException

TESTDATA = [
    ('Dimir Control', 'Dimir Control', ['U', 'B'], 'Control'),
    ('U/B Control', 'Dimir Control', ['U', 'B'], 'Control'),
    ('dimir Control', 'Dimir Control', ['U', 'B'], 'Control'),
    ('U/B Reanimator', 'Dimir Reanimator', ['U', 'B'], 'Control'),
    ('penny dreadful black lifegain', 'Mono Black Lifegain', ['B'], 'Control'),
    ('biovisionary pd', 'Biovisionary', ['G', 'U'], 'Control'),
    ('mono red ashling aggro', 'Mono Red Ashling Aggro', ['R'], 'Aggro'),
    ('penny dreadful esper mill', 'Esper Mill', ['W', 'U', 'B'], 'Unclassified'),
    ('penny dreadful gw tokens', 'Selesnya Tokens', ['W', 'G'], 'Aggro-Combo'),
    ('Jund', 'Jund Control', ['R', 'G', 'B'], 'Control'),
    ('Jund', 'Jund', ['R', 'G', 'B'], None),
    ('RDW', 'Red Deck Wins', ['R'], 'Aggro'),
    ('Red Deck Wins', 'Red Deck Wins', ['R'], 'Aggro'),
    ('WW', 'White Weenie', ['W'], 'Aggro'),
    ('White Weenie', 'White Weenie', ['W'], 'Aggro'),
    ('[pd] Mono B Control', 'Mono Black Control', ['B'], 'Control'),
    ('BR Control', 'Rakdos Control', ['B', 'R'], 'Control'),
    ('b ', 'Mono Black', ['B'], None),
    ('muc', 'Mono Blue Control', ['U'], None),
    ('RDW23', 'Rdw23', ['R'], None), # This isn't ideal but see BWWave for why it's probably right.
    ('Mono B Aristocrats III', 'Mono Black Aristocrats III', ['B'], None),
    ('Mono B Aristocrats IV', 'Mono Black Aristocrats IV', ['B'], None),
    ('Suicide Black', 'Suicide Black', ['B'], None),
    ('Penny Dreadful Sunday RDW', 'Red Deck Wins', ['R'], None),
    ('[Pd][hou] Harvest Quest', 'Harvest Quest', None, None),
    ('Pd_Vehicles', 'Vehicles', None, None),
    ('better red than dead', 'Better Red Than Dead', ['R'], None),
    ('week one rdw', 'Week One Red Deck Wins', ['R'], None),
    ('.ur control', 'Izzet Control', ['U', 'R'], None),
    ('mono g aggro', 'Mono Green Aggro', ['G'], 'Aggro'),
    ('monog ramp', 'Mono Green Ramp', ['G'], 'Aggro'),
    ('Monogreen Creatures', 'Mono Green Creatures', ['G', 'W'], None),
    ('S6 red Deck Wins', 'Red Deck Wins', ['R'], None),
    ('S6red Deck Wins', 'Red Deck Wins', ['R'], None),
    ('Mono-W Soldiers', 'Mono White Soldiers', ['W'], None),
    ('BWWave', 'Bwwave', ['W'], None), # Not ideal but ok.
    ('PD - Archfiend Cycling', 'Archfiend Cycling', None, None),
    ('a red deck but not a net deck', 'A Red Deck but Not a Net Deck', None, None),
    ('Better red than dead', 'Better Red Than Dead', None, None),
    ("Is it Izzet or isn't it?", "Is It Izzet or Isn't It?", None, None),
    ('Rise like a golgari', 'Rise Like a Golgari', ['W', 'U', 'B', 'R', 'G'], None),
    ('BIG RED', 'Big Red', None, None),
    ('big Green', 'Big Green', None, None),
    ('Black Power', 'Mono Black Power', ['U', 'B'], None),
    ('PD', 'Mono Green', ['G'], None),
    ('PD', 'Azorius Control', ['U', 'W'], 'Control'),
    ('PD', 'Azorius', ['U', 'W'], 'Unclassified'),
    ('White Jund', 'White Jund', None, None),
    ('Bant #Value', 'Bant Yisan-Prophet', ['G', 'U', 'W'], 'Yisan-Prophet'),
    ('Yore-Tiller Control', 'Yore-Tiller Control', ['W', 'U', 'B', 'R'], 'Control'),

    # Cases that used to work well under strip-and-replace that no longer do
    # ('White Green', 'Selesnya Aggro', ['W', 'G'], 'Aggro'),
    # ('White Green', 'Selesnya', ['W', 'G'], None),
]

@pytest.mark.parametrize('original_name,expected,colors,archetype_name', TESTDATA)
def test_normalize(original_name: str, expected: str, colors: List[str], archetype_name: str) -> None:
    d = Container({'original_name': original_name,
                   'archetype_name': archetype_name,
                   'colors': colors or []})
    assert deck_name.normalize(d) == expected

def test_remove_pd() -> None:
    assert deck_name.remove_pd('Penny Dreadful Knights') == 'Knights'
    assert deck_name.remove_pd('biovisionary pd') == 'biovisionary'
    assert deck_name.remove_pd('[PD] Mono Black Control') == 'Mono Black Control'

def test_invalid_color() -> None:
    d = Container({'original_name': 'PD',
                   'archetype_name': 'Control',
                   'colors': ['U', 'X']})
    try:
        deck_name.normalize(d)
        assert False
    except InvalidDataException:
        assert True
