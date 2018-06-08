import subprocess
from typing import Dict, List, Union

from flask import url_for
from sqlalchemy import create_engine
from sqlalchemy_utils import create_database, database_exists

from shared import configuration
from shared_web.flask_app import PDFlask

APP = PDFlask(__name__)

APP.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
APP.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{user}:{password}@{host}:{port}/{db}'.format(
    user=configuration.get('mysql_user'),
    password=configuration.get('mysql_passwd'),
    host=configuration.get('mysql_host'),
    port=configuration.get('mysql_port'),
    db=configuration.get('logsite_database'))

from . import db, main, stats, api, views # isort:skip # pylint: disable=wrong-import-position, unused-import

def __create_schema() -> None:
    engine = create_engine(APP.config['SQLALCHEMY_DATABASE_URI'])
    if not database_exists(engine.url):
        create_database(engine.url)
        db.DB.create_all()
    engine.dispose()

APP.config['commit-id'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'])
APP.config['branch'] = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).strip().decode()
APP.config['SECRET_KEY'] = configuration.get('oauth2_client_secret')
APP.config['js_url'] = 'https://pennydreadfulmagic.com/static/js/pd.js'
APP.config['css_url'] = 'https://pennydreadfulmagic.com/static/css/pd.css'
def build_menu() -> List[Dict[str, Union[str, Dict[str, str]]]]:
    menu = [
        {'name': 'Home', 'url': url_for('home')},
        {'name': 'Matches', 'url': url_for('matches')},
        {'name': 'People', 'url': url_for('people')},
        {'name': 'About', 'url': url_for('about')},
    ]
    return menu

APP.config['menu'] = build_menu

__create_schema()
