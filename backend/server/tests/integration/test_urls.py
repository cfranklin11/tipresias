# pylint: disable=missing-docstring

from django.test import Client, TestCase
from django.urls import reverse
import pandas as pd

from server.tests.fixtures import data_factories, factories
from server.models import Prediction


N_MATCHES = 9


class TestUrls(TestCase):
    def setUp(self):
        self.client = Client()

    def test_predictions(self):
        ml_model = factories.MLModelFactory(name="test_estimator")
        matches = [factories.FullMatchFactory() for _ in range(N_MATCHES)]
        prediction_data = pd.concat(
            [
                data_factories.fake_prediction_data(
                    match_data=match, ml_model_name=ml_model.name
                )
                for match in matches
            ]
        )
        predictions = {
            "data": prediction_data.to_dict("records"),
        }

        self.assertEqual(Prediction.objects.count(), 0)

        self.client.post(
            reverse("predictions"), content_type="application/json", data=predictions
        )

        self.assertEqual(Prediction.objects.count(), N_MATCHES)
