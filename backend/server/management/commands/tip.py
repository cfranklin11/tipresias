"""Module for 'tip' command that updates predictions for upcoming AFL matches."""

from django.core.management.base import BaseCommand

from server.tipping import Tipper


class Command(BaseCommand):
    """manage.py command for 'tip' that updates predictions for upcoming AFL matches."""

    help = """
    Check if there are upcoming AFL matches and make predictions on results
    for all unplayed matches in the upcoming/current round.
    """

    def handle(self, *_args, verbose=1, **_kwargs) -> None:  # pylint: disable=W0221
        """Run 'tip' command."""
        tipper = Tipper(verbose=verbose)
        tipper.update_match_data()
        tipper.update_match_predictions()
        tipper.submit_tips()
