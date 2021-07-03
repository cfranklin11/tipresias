# pylint: disable=missing-docstring,redefined-outer-name

from datetime import timedelta, timezone, datetime

import numpy as np
from faker import Faker
from sqlalchemy import select, func
from freezegun import freeze_time
import pytest

from tests.fixtures import data_factories
from tipping.models import Match, TeamMatch, Team


FAKE = Faker()


def test_match_creation(fauna_session):
    match = Match(
        start_date_time=FAKE.date_time(tzinfo=timezone.utc),
        round_number=np.random.randint(1, 100),
        venue=FAKE.company(),
    )
    fauna_session.add(match)
    fauna_session.commit()

    assert match.id is not None


def test_from_future_fixtures(fauna_session):
    fixture_matches = data_factories.fake_fixture_data()
    next_match = fixture_matches.iloc[np.random.randint(0, len(fixture_matches)), :]
    patched_date = next_match["date"].to_pydatetime() - timedelta(days=1)
    upcoming_round_number = next_match["round_number"]
    upcoming_fixture_matches = fixture_matches.query(
        "round_number == @upcoming_round_number"
    )

    with freeze_time(patched_date):
        assert fauna_session.execute(select(func.count(Match.id))).scalar() == 0

        matches = Match.from_future_fixtures(
            fauna_session, upcoming_fixture_matches, upcoming_round_number
        )
        created_match_count = len(matches)

        assert created_match_count == len(
            upcoming_fixture_matches.query("date > @patched_date")
        )

        for match in matches:
            fauna_session.add(match)

        fauna_session.commit()

        # With existing matches in DB
        matches = Match.from_future_fixtures(
            fauna_session, upcoming_fixture_matches, upcoming_round_number
        )

        assert len(matches) == 0
        total_match_count = fauna_session.execute(select(func.count(Match.id))).scalar()
        assert total_match_count == created_match_count


def test_from_future_fixtures_with_skipped_round(fauna_session):
    fixture_matches = data_factories.fake_fixture_data()
    first_match = fixture_matches.iloc[0, :]
    next_match = fixture_matches.iloc[np.random.randint(1, len(fixture_matches)), :]
    patched_date = next_match["date"].to_pydatetime() - timedelta(days=1)
    upcoming_round_number = int(next_match["round_number"]) + 1

    fauna_session.add(
        Match(
            start_date_time=first_match["date"].to_pydatetime(),
            round_number=first_match["round_number"],
            venue=first_match["venue"],
        )
    )
    fauna_session.commit()

    with freeze_time(patched_date):
        with pytest.raises(
            AssertionError,
            match="Expected upcoming round number to be 1 greater than previous round",
        ):
            Match.from_future_fixtures(
                fauna_session, fixture_matches, upcoming_round_number
            )


def test_played_without_results(fauna_session):
    right_now = datetime.now(tz=timezone.utc)
    two_teams = fauna_session.execute(select(Team).limit(2)).scalars().all()

    played_with_results = Match(
        start_date_time=right_now - timedelta(days=1),
        venue=FAKE.company(),
        round_number=1,
    )
    for team in two_teams:
        played_with_results.team_matches.append(
            TeamMatch(team=team, score=np.random.randint(1, 150))
        )

    played_without_results = Match(
        start_date_time=right_now - timedelta(days=1),
        venue=FAKE.company(),
        round_number=1,
    )
    for team in two_teams:
        played_without_results.team_matches.append(TeamMatch(team=team, score=None))

    unplayed = Match(start_date_time=right_now, venue=FAKE.company(), round_number=1)
    for team in two_teams:
        unplayed.team_matches.append(TeamMatch(team=team, score=None))

    fauna_session.add(played_with_results)
    fauna_session.add(played_without_results)
    fauna_session.add(unplayed)
    fauna_session.commit()

    match_query = Match.played_without_results()
    queried_matches = fauna_session.execute(match_query).scalars().all()

    assert len(queried_matches) == 1
    assert queried_matches[0] == played_without_results
