## The Needle Drop Playlist Generator
----------------------------------------

This is a Python script that generates a playlist of albums in Spotify reviewed by the well known online music critic (*as well as the best teeth in the game*) Anthony "Melon" Fantano. His Youtube channel "TheNeedleDrop" is linked [here](https://www.youtube.com/channel/UCt7fwAhXDy3oNFTAzF2o8Pw) if you would like to explore more of his work.

With a command line interface, the user can choose to include specific music **genres** (country, hip hop, etc), critic **score** (1-10, Not Good, Classic, etc.), and **number of days since reviewed**. For more information, use the help flag:

`python3 main.py -h`

## Setup
------------------------------------------------------------------
1.) Install Dependencies

`pip3 install -r requirements.txt`

2.) Get Oauth tokens from Spotify and Youtube. For Spotify information, store them into a .env file with this format:

`SPOTIFY_CLIENT_ID = ""
SPOTIFY_CLIENT_SECRET = ""
SPOTIFY_USER_ID = ""`

Follow this [guide](https://developer.spotify.com/documentation/general/guides/app-settings/) from Spotify to get the necessary information. Token refreshing is handled so no need to keep updating the token in the file.

For Youtube tokens, check out this [guide](https://developers.google.com/youtube/v3/quickstart/python) to help set up the project in their API console. You should be able to download a file named "client_secret_CLIENTID.json." Rename this to "youtube_client_secret.json."

## Running the File
-----------------------------------------------------------
As stated earlier, for more information on the script feel free to run

`python3 main.py -h`

Here are some examples of running this script:

1.) `python3 main.py`
Generates a playlist with default parameters (accepts all scores & albums within the last 7 days).

2.) `python3 main.py -s 8 9 10 -d 365`
This generates a playlist of albums that received the score 8, 9, or 10 within the last 365 days (1 year)

3.) `python3 main.py -s "NOT GOOD" -d 90`

Contains a playlist that had a score of "NOT GOOD" from the last 90 days.


Once the script is finished running, the command line will contain a link that redirects you to the newly created playlist. Have fun listening!!