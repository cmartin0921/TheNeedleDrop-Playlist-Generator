from dotenv import load_dotenv
import os, re, argparse
import datetime
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

class NeedleDropPlaylistMaker():

  def __init__(self):
    self.spotify_access_token = None
    self.youtube_client = None

    self._authorize()

  def _authorize(self) -> None:
    self._setup_youtube_client()
    self._setup_spotify_client()

  def _setup_youtube_client(self) -> None:

    scopes = ["https://www.googleapis.com/auth/youtube.readonly"]
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = "youtube_client_secret.json"

    flow = InstalledAppFlow.from_client_secrets_file(
      client_secrets_file,
      scopes,
      # client_type="web"
    )
    
    flow.run_local_server(port=8080, prompt="consent", authorization_prompt_message="Authorizing...")
    credentials = flow.credentials

    self.youtube_client = build(
      api_service_name,
      api_version,
      credentials=credentials,
    )

  def _setup_spotify_client(self) -> None:

    oauth_handler = spotipy.Spotify(
      auth_manager = SpotifyOAuth(
        client_id = os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri= "https://www.spotify.com/us/home/",
        scope = "playlist-modify-public playlist-modify-private playlist-read-collaborative"
        )
      )

    self.spotify_access_token = oauth_handler.auth_manager.get_cached_token().get("access_token")

  def generate_reviewed_playlist(self, scores=None, days=7, genres=None) -> str:

    """
    Generates a Spotify playlist of albums reviewed by TheNeedleDrop. This is the main function that is called
    to start the process.

    Parameters
    ----------

    scores: List[string]
      Filters albums with OR logic. Taken in as a string rather than int to support "CLASSIC", "NOT GOOD", NOT BAD", etc.
    days: int
      Number of days to include since album was reviewed
    genres: List[string]
      Filters albums with OR logic based on the genres given.

    Returns
    -------
    playlist_url: string
      Returns a Spotify url link to the generated playlist. If the playlist is not created, it returns None

    """

    if isinstance(days, list):
      days = days[0]
    lower_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    upper_date = datetime.datetime.now(datetime.timezone.utc)

    uploaded_vids = list(
        filter(
            lambda v: (
                lower_date
                <= datetime.datetime.strptime(
                    v["contentDetails"]["videoPublishedAt"], "%Y-%m-%dT%H:%M:%S%z"
                )
                <= upper_date
            )
            and (re.compile("|".join(["ALBUM REVIEW", "NOT GOOD", "NOT BAD"])).findall(v["snippet"]["title"]))
            and (self._parse_fantano_score(v) in scores if scores else True)
            and (self._is_valid_genre(v["extracted_info"].get("genre"), genres)),
            self.get_needledrop_uploads(),
        )
    )

    if len(uploaded_vids) == 0:
      print("Unable to find any album reviews with given parameters..")
      return

    # GET album ids through Spotify's search
    albums_found = 0
    tracklist_uris = []
    for vid_info in uploaded_vids:
      query = f'{vid_info["extracted_info"].get("album")} {vid_info["extracted_info"].get("artist")}'
      response_json = self.get_album_search(query)

      if response_json:
        if len(response_json["albums"]["items"]) != 0:
          # Need to access track uris and append to list instead
          current_album_track_list_uris = self.get_album_tracks(response_json["albums"]["items"][0]["id"])
          tracklist_uris.extend(current_album_track_list_uris)
          albums_found += 1
        # else:
        #   print(f"Cannot find {query}")
    print(f"{albums_found} albums found in Spotify")

    if len(tracklist_uris) > 0:
      # POST spotify playlist
      lower_date_string = lower_date.strftime("%m/%d/%Y")
      upper_date_string = upper_date.strftime("%m/%d/%Y")
      playlist_title = f"TND List Maker: {lower_date_string} - {upper_date_string}"
      playlist_description = f"Score: {','.join(scores) if scores is not None else 'All'}. Genre: {genres if genres is not None else 'All'}"

      if self.find_existing_playlist(playlist_title, playlist_description):
        print("Playlist already created. Exiting...")
        return

      playlist_create_endpoint = f"https://api.spotify.com/v1/users/{os.getenv('SPOTIFY_USER_ID')}/playlists"
      payload = {
        "name": playlist_title,
        "description": playlist_description,
        "public": False
      }

      try:
        playlist_create_req = requests.post(
          playlist_create_endpoint,
          headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.spotify_access_token}"
          },
          data = json.dumps(payload)
        )
        playlist_create_req.raise_for_status()
      except requests.exceptions.RequestException as e:
        raise SystemExit(e)

      playlist_create_json = playlist_create_req.json()
      playlist_id = playlist_create_json["id"]
    else:
      print("No albums found in Spotify")
      return

    self.add_tracks_to_playlist(tracklist_uris, playlist_id)

    return playlist_create_json["external_urls"]["spotify"]

  def get_needledrop_uploads(self) -> list:

    """
    Makes a Youtube API requests to fetch in all the uploaded videos in the channel TheNeedleDrop

    Returns
    -------
    
    uploaded_vids: List[dict]
      Returns a list of video information in .json format
    
    """

    # Fetch TheNeedleDrop information
    channel_info_req = self.youtube_client.channels().list(
      part="id,contentDetails",
      forUsername="theneedledrop"
    )
    channel_info_res = channel_info_req.execute()
    channel_uploads_list_id = channel_info_res['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    # Fetch uploaded videos from TheNeedleDrop
    uploads_req = self.youtube_client.playlistItems().list(
      part="contentDetails, id, snippet",
      playlistId=channel_uploads_list_id,
      maxResults=50,
    )
    uploads_res = uploads_req.execute()
    uploaded_vids = []
    page_token = None
    while True:
      uploads_req = self.youtube_client.playlistItems().list(
        part="contentDetails, id, snippet",
        playlistId=channel_uploads_list_id,
        maxResults=50,
        pageToken=page_token
      )
      uploads_res = uploads_req.execute()
      for i in uploads_res["items"]:
        i["extracted_info"] = self._extract_video_description(i)

        
      uploaded_vids.extend(uploads_res["items"])

      if uploads_res.get('nextPageToken'):
        page_token = uploads_res.get('nextPageToken')
      else:
        break

    return uploaded_vids

  def add_tracks_to_playlist(self, tracklist_uris, playlist_id) -> None:

    """
    Adds all tracklists found on Spotify onto a newly created playlist.

    Parameters
    ----------

    tracklist_uris: List[dict]
      List of dictionaries of information about each track on the albums to add to the playlist
      
    playlist_id: int
      Id of newly created Spotify playlist

    """

    endpoint = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    current_idx = 0

    try:
      while current_idx < len(tracklist_uris):
        upper_idx = min(current_idx+100, len(tracklist_uris))
        payload = {
          "uris": tracklist_uris[current_idx:upper_idx]
        }
        add_to_playlist_req = requests.post(
          endpoint,
          headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.spotify_access_token}"
          },
          data = json.dumps(payload)
        )
        add_to_playlist_req.raise_for_status()
        current_idx += 100
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

  def get_album_search(self, query) -> dict:

    """
    Makes a Spotify web API request to find the wanted album using its search functionality

    Parameters
    ----------
    query: string
      Contains the album name
        
    Returns
    -------
    dict
      .json response from the API on information about the album
    """

    if query is None:
      print("Empty string to be put into the query")
      return None

    # Spotify: Search for an Item
    album_search_endpoint = f"https://api.spotify.com/v1/search?q={query}&type=album"
    # Assumption: the first item returned is the best/correct result
    payload = {
      "q": query,
      "type": "album"
    }

    try:
      search_req = requests.get(
        album_search_endpoint,
        headers = {
          "Content-Type": "application/json",
          "Authorization": f"Bearer {self.spotify_access_token}"
        },
        params = payload
      )
      search_req.raise_for_status()
      # search_res = search_req.json()
      # search_json = list(filter(lambda item: item["type"] == "album", search_res["albums"]["items"]))
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

    return search_req.json()

  def get_album_tracks(self, album_id) -> list:

    """
    Makes a Spotify web API request to parses out the tracklist of the album

    Parameters
    ----------
    album_id: int
      Id of Spotify album
        
    Returns
    -------
    tracklist_uris: list[str]
      List or tracklist uris of the given album
    """

    endpoint = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
    payload = {
      "limit": 20
    }

    try:
      album_req = requests.get(
        endpoint,
        headers = {
          "Content-Type": "application/json",
          "Authorization": f"Bearer {self.spotify_access_token}"
        },
        params = payload
      )
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

    album_res_json = album_req.json()

    tracklist_uris = []
    for item in album_res_json["items"]:
      if item.get("type") == "track":
        tracklist_uris.append(item["uri"])
    
    return tracklist_uris

  def find_existing_playlist(self, playlist_title, description) -> bool:

    """
    Checks if the user already has an existing playlist with the same title and description information.

    Parameters
    ----------
    playlist_title: string
      Name of playlist to look for

    description: string
      Description of the playlist to look for
        
    Returns
    -------
    bool
      True if playlist is found. False if playlist doesn't exist.
    """

    find_playlist_endpoint = f"https://api.spotify.com/v1/me/playlists"
    try:
      user_playlists_req = requests.get(
        find_playlist_endpoint,
        headers = {
          "Content-Type": "application/json",
          "Authorization": f"Bearer {self.spotify_access_token}"
        }
      )
      user_playlists_req.raise_for_status()
    except requests.exceptions.RequestException as e:
      raise SystemExit(e)

    user_playlists_json = user_playlists_req.json()
    # Check if playlist has already been created. Check based on playlist title/name & description
    if len(user_playlists_json["items"]) > 0:
      matching_playlist = list(filter(lambda x: x["name"] == playlist_title and x["description"] == description, user_playlists_json["items"]))
      if len(matching_playlist) > 0:
        return True

    return False

  @staticmethod
  def _parse_fantano_score(playlist_item) -> str:

    """
    Extracts the score given by TheNeedleDrop based on the video description

    Parameters
    ----------
    playlist_item: dict
      Youtube API PlaylistItem object 
        
    Returns
    -------
    score: str
      If included in the video description, returns the score of the album
    """
    
    score_pattern = "[a-zA-Z0-9 ]+/10"

    found_score = re.search(score_pattern, playlist_item["snippet"]["description"])
    if found_score:
      return found_score.group(0).split("/")[0]
    
    return None

  @staticmethod
  def _extract_video_description(video_obj) -> dict:

    """
    Extracts album name, artists, and genre of the album reviewed

    Parameters
    ----------
    playlist_item: dict
      Youtube API PlaylistItem object 
        
    Returns
    -------
    album_info: dict
      Dictionary containing these information
        {
          "artist": str,
          "album": str,
          "genre": list[str]
        }
    """

    regex_pattern = re.compile(r"^(.+)-(.+)\/(.+)\/(.+)[\/]?" , re.MULTILINE)
    url_pattern = re.compile(r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+", re.MULTILINE)

    split_description = video_obj["snippet"]["description"].split('\n')
    removed_urls = list(map(lambda x: re.sub(url_pattern, "", x, re.MULTILINE), split_description))
    info = list(filter(lambda x: re.search(regex_pattern, x), removed_urls))

    album_info = {}
    if info:
      info_split = info[0].split("/")
      album_info["artist"] = info_split[0].split("-")[0].strip()
      album_info["album"] = info_split[0].split("-")[-1].strip()
      album_info["genre"] = list(map(str.strip, info_split[-1].split(",")))
    # else:
    #   print("Video description doesn't contain album info")

    return album_info

  @staticmethod
  def _is_valid_genre(genre_list, wanted_genre) -> bool:

    """
    Checks if the user already has an existing playlist with the same title and description information.

    Parameters
    ----------
    genre_list: list[str]
      Genres that the album is in, according to TheNeedleDrop's video description

    description: list[str]
      List of genres user wants to contain into the playlist
        
    Returns
    -------
    bool
      True if the album is within the genres user wants. False if otherwise.
    """

    if not wanted_genre:
      return True

    genre_list = list(map(lambda g: g.lower().strip(), genre_list))
    wanted_genre = list(map(lambda g: g.lower().strip(), wanted_genre))
    pattern = re.compile("|".join(wanted_genre))

    for genre in genre_list:
      if pattern.findall(genre):
        return True

    return False

if __name__ == "__main__":
  load_dotenv()

  parser = argparse.ArgumentParser(
    description="This is a script that generates a playlist of albums (available in Spotify only) reviewed by the youtube channel 'theneedledrop': https://www.youtube.com/channel/UCt7fwAhXDy3oNFTAzF2o8Pw"
    )
    
  parser.add_argument(
    '-g', '--genres', type=str,
    help="Genres wanted in the playlist. If no genre is specified, then it accepts all album types.",
    nargs="*", required=False
    )
  parser.add_argument(
    '-s', '--scores', type=str,
    help="Score given by the youtube channel to include in the playlist.",
    nargs="*", required=False
    )
  parser.add_argument(
    '-d', '--days', type=int,
    help="Max number of days (from today) since the album was reviewed. If not specified, then default is 7 days.",
    nargs=1, required=False
    )
  args = parser.parse_args()

  args_dict = {k: v for k, v in vars(args).items() if v != None}

  playlist_maker = NeedleDropPlaylistMaker()
  new_playlist_url = playlist_maker.generate_reviewed_playlist(**args_dict)

  if new_playlist_url:
    print(f"New playlist created: {new_playlist_url}")