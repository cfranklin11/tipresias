"""Module for data transformations and internal conventions"""

TEAM_TRANSLATIONS = {
    "Tigers": "Richmond",
    "Blues": "Carlton",
    "Demons": "Melbourne",
    "Giants": "GWS",
    "Suns": "Gold Coast",
    "Bombers": "Essendon",
    "Swans": "Sydney",
    "Magpies": "Collingwood",
    "Kangaroos": "North Melbourne",
    "Crows": "Adelaide",
    "Bulldogs": "Western Bulldogs",
    "Dockers": "Fremantle",
    "Power": "Port Adelaide",
    "Saints": "St Kilda",
    "Eagles": "West Coast",
    "Lions": "Brisbane",
    "Cats": "Geelong",
    "Hawks": "Hawthorn",
    "Adelaide Crows": "Adelaide",
    "Brisbane Lions": "Brisbane",
    "Gold Coast Suns": "Gold Coast",
    "GWS Giants": "GWS",
    "Geelong Cats": "Geelong",
    "West Coast Eagles": "West Coast",
    "Sydney Swans": "Sydney",
}
VENUE_TRANSLATIONS = {
    "AAMI": "AAMI Stadium",
    "ANZ": "ANZ Stadium",
    "Adelaide": "Adelaide Oval",
    "Aurora": "UTAS Stadium",
    "Aurora Stadium": "UTAS Stadium",
    "Blacktown": "Blacktown International",
    "Blundstone": "Blundstone Arena",
    "Cazaly's": "Cazaly's Stadium",
    "Domain": "Domain Stadium",
    "Etihad": "Etihad Stadium",
    "GMHBA": "GMHBA Stadium",
    "Gabba": "Gabba",
    "Jiangwan": "Jiangwan Stadium",
    "MCG": "MCG",
    "Mars": "Mars Stadium",
    "Metricon": "Metricon Stadium",
    "Perth": "Optus Stadium",
    "SCG": "SCG",
    "Spotless": "Spotless Stadium",
    "StarTrack": "Manuka Oval",
    "TIO": "TIO Stadium",
    "UTAS": "UTAS Stadium",
    "Westpac": "Westpac Stadium",
    "TIO Traegar Park": "TIO Stadium",
}
TEAM_NAMES = sorted(["Fitzroy", "University"] + list(set(TEAM_TRANSLATIONS.values())))
ROUND_TYPES = ["Finals", "Regular"]

