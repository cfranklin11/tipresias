# pylint: disable=missing-docstring

from unittest import TestCase
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

from tests.fixtures import data_factories
from tipping import data_export, settings


N_MATCHES = 5
YEAR_RANGE = (2016, 2017)


class TestDataExport(TestCase):
    def setUp(self):
        self.data_export = data_export

    @patch("tipping.data_export.requests")
    def test_update_fixture_data(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "Stuff happened"

        mock_requests.post = MagicMock(return_value=mock_response)

        url = settings.TIPRESIAS_APP + "/fixtures"
        fake_fixture = data_factories.fake_fixture_data(N_MATCHES, YEAR_RANGE)
        upcoming_round = np.random.randint(1, 24)
        self.data_export.update_fixture_data(fake_fixture, upcoming_round)

        # It posts the data
        mock_requests.post.assert_called_with(
            url,
            json={
                "upcoming_round": upcoming_round,
                "data": fake_fixture.to_dict("records"),
            },
        )

        with self.subTest("when the status code isn't 2xx"):
            mock_response.status_code = 400

            with self.assertRaisesRegex(Exception, "Bad response"):
                self.data_export.update_fixture_data(fake_fixture, upcoming_round)

    @patch("tipping.data_export.requests")
    def test_update_match_predictions(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "Stuff happened"

        mock_requests.post = MagicMock(return_value=mock_response)

        url = settings.TIPRESIAS_APP + "/predictions"
        fake_predictions = pd.concat(
            [data_factories.fake_prediction_data() for _ in range(N_MATCHES)]
        )
        self.data_export.update_match_predictions(fake_predictions)

        # It posts the data
        mock_requests.post.assert_called_with(
            url, json={"data": fake_predictions.to_dict("records")}
        )

        with self.subTest("when the status code isn't 2xx"):
            mock_response.status_code = 400

            with self.assertRaisesRegex(Exception, "Bad response"):
                self.data_export.update_match_predictions(fake_predictions)

    @patch("tipping.data_export.requests")
    def test_update_match_results(self, mock_requests):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "Stuff happened"

        mock_requests.post = MagicMock(return_value=mock_response)

        url = settings.TIPRESIAS_APP + "/matches"
        fake_matches = data_factories.fake_match_results_data(N_MATCHES, YEAR_RANGE)
        self.data_export.update_match_results(fake_matches)

        # It posts the data
        mock_requests.post.assert_called_with(
            url, json={"data": fake_matches.to_dict("records")}
        )

        with self.subTest("when the status code isn't 2xx"):
            mock_response.status_code = 400

            with self.assertRaisesRegex(Exception, "Bad response"):
                self.data_export.update_match_predictions(fake_matches)
