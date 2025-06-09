from apify_client import ApifyClient
from config import settings

def search_instagram_posts_by_keyword(keyword):
    """
    Search for Instagram posts by keyword using hashtag search
    """
    # Initialize the ApifyClient with your API token
    client = ApifyClient(settings.apify_api_token)

    # Prepare the Actor input for keyword search
    run_input = {
        "addParentData": False,
        "enhanceUserSearchWithFacebookPage": False,
        "isUserReelFeedURL": False,
        "isUserTaggedFeedURL": False,
        "resultsLimit": 2,
        "resultsType": "details",
        "search": keyword,
        "searchLimit": 5,
        "searchType": "hashtag"
    }

    # Run the Actor and wait for it to finish
    run = client.actor("apify/instagram-scraper").call(run_input=run_input)

    # Fetch and return all posts from the search results
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        posts.append(item)
    
    return posts
