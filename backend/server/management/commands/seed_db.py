"""Django command for seeding the DB with match & prediction data"""

import itertools
from datetime import datetime
from functools import partial, reduce
from pydoc import locate
from typing import Tuple, List, Optional, Type, Iterator
from mypy_extensions import TypedDict
import pandas as pd
import numpy as np
from django import utils
from django.core.management.base import BaseCommand

from server.data_readers import FootywireDataReader
from server.models import Team, Match, TeamMatch, MLModel, Prediction
from server.ml_models import ml_model
from server.ml_models.betting_model import BettingModel, BettingModelData
from server.ml_models.match_model import MatchModel, MatchModelData
from server.ml_models.all_model import AllModel, AllModelData
from server.ml_models.player_model import PlayerModel, PlayerModelData
from server.ml_models import AvgModel

FixtureData = TypedDict(
    "FixtureData",
    {
        "date": pd.Timestamp,
        "season": int,
        "season_game": int,
        "round": int,
        "home_team": str,
        "away_team": str,
        "venue": str,
    },
)
EstimatorTuple = Tuple[ml_model.MLModel, Type[ml_model.MLModelData]]

YEAR_RANGE = "2011-2017"
ESTIMATORS: List[EstimatorTuple] = [
    (BettingModel(name="betting_data"), BettingModelData),
    (MatchModel(name="match_data"), MatchModelData),
    (PlayerModel(name="player_data"), PlayerModelData),
    (AllModel(name="all_data"), AllModelData),
    (AvgModel(name="tipresias"), AllModelData),
]
NO_SCORE = 0
JAN = 1
DEC = 12
RESCUE_LIMIT = datetime(2019, 2, 1)
DODGY_SEASONS = [2012, 2013, 2014, 2016]


class Command(BaseCommand):
    help = "Seed the database with team, match, and prediction data."

    def __init__(
        self,
        *args,
        data_reader=FootywireDataReader(),
        estimators: List[EstimatorTuple] = ESTIMATORS,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.data_reader = data_reader
        self.estimators = estimators

    def handle(  # pylint: disable=W0221
        self, *_args, year_range: str = YEAR_RANGE, verbose: int = 1, **_kwargs
    ) -> None:  # pylint: disable=W0613
        self.verbose = verbose  # pylint: disable=W0201

        if self.verbose == 1:
            print("\nSeeding DB...\n")

        years_list = [int(year) for year in year_range.split("-")]

        if len(years_list) != 2 or not all(
            [len(str(year)) == 4 for year in years_list]
        ):
            raise ValueError(
                "Years argument must be of form 'yyyy-yyyy' where each 'y' is "
                f"an integer. {year_range} is invalid."
            )

        # A little clunky, but mypy complains when you create a tuple with tuple(),
        # which is open-ended, then try to use a restricted tuple type
        year_range_tuple = (years_list[0], years_list[1])

        fixture_data_frame = self.data_reader.get_fixture(year_range=year_range_tuple)

        # Putting saving records in a try block, so we can go back and delete everything
        # if an error is raised
        try:
            self.__create_teams(fixture_data_frame)
            ml_models = self.__create_ml_models()
            self.__create_matches(fixture_data_frame.to_dict("records"))
            self.__make_predictions(year_range_tuple, ml_models=ml_models)

            if self.verbose == 1:
                print("\n...DB seeded!\n")
        except:
            print("\nRolling back DB changes...")
            Team.objects.all().delete()
            MLModel.objects.all().delete()
            Match.objects.all().delete()
            print("...DB unseeded!\n")

            raise

    def __create_teams(self, fixture_data: pd.DataFrame) -> None:
        team_names = np.unique(fixture_data[["home_team", "away_team"]].values)
        teams = [self.__build_team(team_name) for team_name in team_names]

        if not any(teams):
            raise ValueError("Something went wrong and no teams were saved.")

        Team.objects.bulk_create(teams)

        if self.verbose == 1:
            print("Teams seeded!")

    def __create_ml_models(self) -> List[MLModel]:
        ml_models = [
            self.__build_ml_model(estimator, data_class)
            for estimator, data_class in self.estimators
        ]

        if not any(ml_models):
            raise ValueError("Something went wrong and no ML models were saved.")

        MLModel.objects.bulk_create(ml_models)

        if self.verbose == 1:
            print("ML models seeded!")

        return ml_models

    def __create_matches(self, fixture_data: List[FixtureData]) -> None:
        if not any(fixture_data):
            raise ValueError("No match data found.")

        team_matches = [self.__build_match(match_data) for match_data in fixture_data]
        team_matches_to_save = reduce(
            lambda acc_list, curr_list: acc_list + curr_list, team_matches
        )

        if not any(team_matches):
            raise ValueError("Something went wrong, and no team matches were saved.")

        TeamMatch.objects.bulk_create(team_matches_to_save)

        if self.verbose == 1:
            print("Match data saved!")

    def __build_match(self, match_data: FixtureData) -> List[TeamMatch]:
        raw_date = match_data["date"].to_pydatetime()

        # 'make_aware' raises error if datetime already has a timezone
        if raw_date.tzinfo is None or raw_date.tzinfo.utcoffset(raw_date) is None:
            match_date = utils.timezone.make_aware(raw_date)
        else:
            match_date = raw_date

        match: Match = Match(
            start_date_time=match_date,
            round_number=int(match_data["round"]),
            venue=match_data["venue"],
        )

        match.full_clean()
        match.save()

        return self.__build_team_match(match, match_data)

    def __make_predictions(
        self,
        year_range: Tuple[int, int],
        ml_models: Optional[List[MLModel]] = None,
        round_number: Optional[int] = None,
    ) -> None:
        ml_models = ml_models or MLModel.objects.all()

        if ml_models is None or not any(ml_models):
            if self.verbose == 1:
                raise ValueError(
                    "\tCould not find any ML models in DB to make predictions."
                )

        make_model_predictions = partial(
            self.__make_model_predictions, year_range, round_number=round_number
        )
        model_predictions_list = [
            make_model_predictions(ml_model_record) for ml_model_record in ml_models
        ]
        model_predictions = itertools.chain.from_iterable(model_predictions_list)

        if not any(model_predictions):
            raise ValueError("Could not find any predictions to save to the DB.")

        Prediction.objects.bulk_create(list(model_predictions))

        if self.verbose == 1:
            print("\nPredictions saved!")

    def __make_model_predictions(
        self,
        year_range: Tuple[int, int],
        ml_model_record: MLModel,
        round_number: Optional[int] = None,
    ) -> Iterator[Prediction]:
        if self.verbose == 1:
            print(f"\nMaking predictions with {ml_model_record.name}...")

        estimator = self.__estimator(ml_model_record)
        data_class = locate(ml_model_record.data_class_path)

        data = data_class()

        make_year_predictions = partial(
            self.__make_year_predictions,
            ml_model_record,
            estimator,
            data,
            round_number=round_number,
        )

        return itertools.chain.from_iterable(
            [make_year_predictions(year) for year in range(*year_range)]
        )

    # TODO: Got the following error when trying to implement multiprocessing:
    # TypeError: cannot serialize '_io.TextIOWrapper' object
    # Not too sure on the cause, but it works okay for now (it's just slow).
    def __make_year_predictions(
        self,
        ml_model_record: MLModel,
        estimator: ml_model.MLModel,
        data: ml_model.MLModelData,
        year: int,
        round_number: Optional[int] = None,
    ) -> List[Prediction]:
        if self.verbose == 1:
            print(f"\tMaking predictions for {year}...")

        matches_to_predict = Match.objects.filter(start_date_time__year=year)

        if matches_to_predict is None or not any(matches_to_predict):
            if self.verbose == 1:
                print(
                    f"\tCould not find any matches from season {year} to make predictions for."
                )

            return []

        data.train_years = (None, year - 1)
        data.test_years = (year, year)
        data_row_slice = (slice(None), year, slice(round_number, round_number))
        prediction_data = self.__predict(estimator, data, data_row_slice)

        build_match_prediction = partial(
            self.__build_match_prediction, ml_model_record, prediction_data
        )

        return [build_match_prediction(match) for match in matches_to_predict]

    @staticmethod
    def __predict(
        estimator: ml_model.MLModel,
        data: ml_model.MLModelData,
        data_row_slice: Tuple[slice, int, slice],
    ):
        X_train, y_train = data.train_data()
        X_test, _ = data.test_data()

        # On the off chance that we try to run predictions for years that have no relevant
        # prediction data
        if X_train.empty or y_train.empty or X_test.empty:
            return []

        estimator.fit(X_train, y_train)

        y_pred = estimator.predict(X_test)

        return data.data.loc[data_row_slice, :].assign(predicted_margin=y_pred)

    @staticmethod
    def __build_ml_model(
        estimator: ml_model.MLModel, data_class: Type[ml_model.MLModelData]
    ) -> MLModel:
        ml_model_record = MLModel(
            name=estimator.name, data_class_path=data_class.class_path()
        )
        ml_model_record.full_clean()

        return ml_model_record

    @staticmethod
    def __build_team(team_name: str) -> Team:
        team = Team(name=team_name)
        team.full_clean()

        return team

    @staticmethod
    def __build_team_match(match: Match, match_data: FixtureData) -> List[TeamMatch]:
        home_team = Team.objects.get(name=match_data["home_team"])
        away_team = Team.objects.get(name=match_data["away_team"])

        home_team_match = TeamMatch(
            team=home_team, match=match, at_home=True, score=NO_SCORE
        )
        away_team_match = TeamMatch(
            team=away_team, match=match, at_home=False, score=NO_SCORE
        )

        home_team_match.clean_fields()
        home_team_match.clean()
        away_team_match.clean_fields()
        away_team_match.clean()

        return [home_team_match, away_team_match]

    @staticmethod
    def __build_match_prediction(
        ml_model_record: MLModel, prediction_data: pd.DataFrame, match: Match
    ) -> Prediction:
        home_team = match.teammatch_set.get(at_home=True).team
        away_team = match.teammatch_set.get(at_home=False).team

        match_prediction = prediction_data.loc[
            ([home_team.name, away_team.name], match.year, match.round_number),
            "predicted_margin",
        ]

        predicted_home_margin = match_prediction.loc[home_team.name].iloc[0]
        predicted_away_margin = match_prediction.loc[away_team.name].iloc[0]

        # predicted_margin is always positive as its always associated with predicted_winner
        predicted_margin = match_prediction.abs().mean()

        if predicted_home_margin > predicted_away_margin:
            predicted_winner = home_team
        elif predicted_away_margin > predicted_home_margin:
            predicted_winner = away_team
        else:
            raise ValueError(
                "Predicted home and away margins are equal, which is basically impossible, "
                "so figure out what's going on:\n"
                f"home_team = {home_team.name}\n"
                f"away_team = {away_team.name}\n"
                "data ="
                f"{match_prediction}"
            )

        prediction = Prediction(
            match=match,
            ml_model=ml_model_record,
            predicted_margin=predicted_margin,
            predicted_winner=predicted_winner,
        )

        prediction.clean_fields()
        prediction.clean()

        return prediction

    @staticmethod
    def __estimator(ml_model_record: MLModel) -> ml_model.MLModel:
        if ml_model_record.name == "betting_data":
            return BettingModel(name=ml_model_record.name)
        if ml_model_record.name == "match_data":
            return MatchModel(name=ml_model_record.name)
        if ml_model_record.name == "player_data":
            return PlayerModel(name=ml_model_record.name)
        if ml_model_record.name == "all_data":
            return AllModel(name=ml_model_record.name)
        if ml_model_record.name == "tipresias":
            return AvgModel(name=ml_model_record.name)

        raise ValueError(f"{ml_model_record.name} is not a recognized ML model name.")
