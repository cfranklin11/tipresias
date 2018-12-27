"""Django command for seeding the DB with match & prediction data"""

from functools import partial
from typing import Sequence, Callable, Generator, Tuple, List
from mypy_extensions import TypedDict
import pandas as pd
import numpy as np
from django.core.management.base import BaseCommand
from django.utils import timezone

from project.settings.common import DATA_DIR
from server.data_processors import FitzroyDataReader
from server.models import Team, Match, TeamMatch, MLModel, Prediction

TEAM_COLUMNS = ["home_team", "away_team"]
MATCH_COLUMNS = ["date", "round_number"]
TEAM_MATCH_COLUMNS = ["home_points", "away_points"]
COLUMNS = TEAM_COLUMNS + MATCH_COLUMNS + TEAM_MATCH_COLUMNS + ["season"]

FitzroyRecord = TypedDict(
    "FitzroyRecord",
    {
        "game": float,
        "date": float,
        "round": str,
        "home_team": str,
        "home_goals": int,
        "home_behinds": int,
        "home_points": int,
        "away_team": str,
        "away_goals": int,
        "away_behinds": int,
        "away_points": int,
        "venue": str,
        "margin": int,
        "season": float,
        "round_type": str,
        "round_number": int,
    },
)
PredictionRecord = TypedDict(
    "PredictionRecord",
    {
        "home_team": str,
        "away_team": str,
        "model": str,
        "predicted_home_margin": int,
        "predicted_home_win": int,
    },
)

UnzippedGroups = Tuple[Sequence[Sequence[TeamMatch]], Sequence[Sequence[Prediction]]]


class Command(BaseCommand):
    help = "Seed the database with team, match, and prediction data."

    def handle(self, *_args, **_kwargs) -> None:  # pylint disable=W0613,R0194
        print("Seeding DB...\n")

        prediction_data_frame: pd.DataFrame = pd.read_csv(
            f"{DATA_DIR}/model_predictions.csv"
        )
        max_prediction_year = prediction_data_frame["year"].max()
        min_prediction_year = prediction_data_frame["year"].min()

        fitzroy = FitzroyDataReader()
        match_results: pd.DataFrame = fitzroy.match_results()
        match_filter = (match_results["season"] >= min_prediction_year) & (
            match_results["season"] <= max_prediction_year
        )
        # We don't need to save match/prediction data going all the way back
        filtered_matches = match_results.loc[match_filter, COLUMNS].assign(
            date=self.__convert_to_datetime
        )

        self.__seed_teams(filtered_matches)
        print("teams seeded!")

        self.__seed_ml_models(prediction_data_frame)
        print("ml_models seeded!")

        get_match_predictions = partial(
            self.__get_match_predictions, prediction_data_frame
        )

        build_team_matches_and_predictions = partial(
            self.__build_team_matches_and_predictions, get_match_predictions
        )

        # Zipping groups team_matches & predictions together
        team_match_groups, prediction_groups = zip(
            *[  # pylint disable=C0301
                build_team_matches_and_predictions(record)
                for record in filtered_matches.to_dict("records")
            ]
        )

        # Sometimes the data doesn't quite match up, creating an inconsistent number
        # of elements per group, so we have to convert each group to an array
        # individually then concatenate
        team_matches: np.array = (
            np.concatenate([np.array(group) for group in team_match_groups])
        )

        predictions: np.array = (
            np.concatenate([np.array(group) for group in prediction_groups])
        )

        TeamMatch.objects.bulk_create(list(team_matches))
        print("team_matches seeded!")

        Prediction.objects.bulk_create(list(predictions))
        print("predictions seeded!")

        print("\n...DB seeded!")

    def __build_team_matches_and_predictions(
        self,
        get_match_predictions: Callable[[FitzroyRecord], List[PredictionRecord]],
        record: FitzroyRecord,
    ) -> Tuple[Sequence[TeamMatch], Sequence[Prediction]]:
        prediction_data = get_match_predictions(record)

        home_team: Team = Team.objects.get(name=record["home_team"])
        away_team: Team = Team.objects.get(name=record["away_team"])

        match: Match = Match(
            # Not setting to timezone of the match location, because I can't be bothered,
            # but may add that level of granularity if/when I add venue data
            start_date_time=timezone.make_aware(record["date"]),
            round_number=record["round_number"],
        )
        match.clean()
        match.save()

        build_prediction = partial(self.__build_prediction, match, home_team, away_team)

        team_matches = self.__build_team_matches(match, home_team, away_team, record)
        predictions: Generator[Prediction, None, None] = (
            build_prediction(prediction_datum) for prediction_datum in prediction_data
        )

        return team_matches, tuple(predictions)

    def __build_prediction(
        self,
        match: Match,
        home_team: Team,
        away_team: Team,
        prediction_datum: PredictionRecord,
    ) -> Prediction:
        ml_model: MLModel = MLModel.objects.get(name=prediction_datum["model"])

        prediction: Prediction = Prediction(
            match=match,
            ml_model=ml_model,
            predicted_winner=self.__winning_team(
                home_team, away_team, prediction_datum
            ),
            predicted_margin=self.__winning_margin(prediction_datum),
        )
        prediction.clean()

        return prediction

    def __seed_ml_models(self, prediction_data: pd.DataFrame) -> None:
        ml_names: Sequence[str] = prediction_data["model"].drop_duplicates()
        ml_models: List[MLModel] = [
            self.__build_ml_model(ml_name) for ml_name in ml_names
        ]

        MLModel.objects.bulk_create(ml_models)

    def __seed_teams(self, match_results: pd.DataFrame) -> None:
        team_names: Sequence[str] = match_results["home_team"].drop_duplicates()
        teams: List[Team] = [self.__build_team(team_name) for team_name in team_names]

        Team.objects.bulk_create(teams)

    @staticmethod
    def __convert_to_datetime(data_frame: pd.DataFrame) -> pd.DataFrame:
        return (
            pd
            # datetime unit must be day, because match data doesn't include time info
            .to_datetime(data_frame["date"], unit="D").dt.to_pydatetime()
        )

    @staticmethod
    def __build_team(team_name: str) -> Team:
        team = Team(name=team_name)
        team.full_clean()

        return team

    @staticmethod
    def __build_ml_model(model_name: str) -> MLModel:
        ml_model = MLModel(name=model_name)
        ml_model.full_clean()

        return ml_model

    @staticmethod
    def __get_match_predictions(
        data_frame: pd.DataFrame, record: FitzroyRecord
    ) -> List[PredictionRecord]:
        return data_frame.loc[
            (data_frame["year"] == record["season"])
            & (data_frame["round_number"] == record["round_number"])
            & (data_frame["home_team"] == record["home_team"])
            & (data_frame["away_team"] == record["away_team"]),
            [
                "home_team",
                "away_team",
                "predicted_home_margin",
                "predicted_home_win",
                "model",
            ],
        ].to_dict("records")

    @staticmethod
    def __winning_team(
        home_team: Team, away_team: Team, prediction_datum: PredictionRecord
    ) -> Team:
        predicted_home_win = prediction_datum["predicted_home_win"] == 1

        if predicted_home_win:
            if prediction_datum["home_team"] != home_team.name:
                raise ValueError(
                    "Prediction home team name "
                    f"{prediction_datum['home_team']} doesn't "
                    f"match home team record {home_team.name}"
                )

            return home_team

        if prediction_datum["away_team"] != away_team.name:
            raise ValueError(
                "Prediction home team name "
                f"{prediction_datum['home_team']} doesn't "
                f"match home team record {home_team.name}"
            )
        return away_team

    @staticmethod
    def __winning_margin(prediction_datum: PredictionRecord) -> int:
        predicted_home_win: bool = prediction_datum["predicted_home_win"] == 1

        if predicted_home_win:
            return int(prediction_datum["predicted_home_margin"])

        return int(prediction_datum["predicted_home_margin"] * -1)

    @staticmethod
    def __build_team_matches(
        match: Match, home_team: Team, away_team: Team, record: FitzroyRecord
    ) -> Tuple[TeamMatch, TeamMatch]:
        home_team_match = TeamMatch(
            team=home_team, match=match, at_home=True, score=record["home_points"]
        )
        away_team_match = TeamMatch(
            team=away_team, match=match, at_home=False, score=record["away_points"]
        )

        home_team_match.clean()
        away_team_match.clean()

        return home_team_match, away_team_match
