from apify_client import ApifyClient
from config import settings
import os

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
        "searchType": "hashtag",
        "onlyPostsNewerThan": "12 months"
    }

    # Run the Actor and wait for it to finish
    run = client.actor("apify/instagram-scraper").call(run_input=run_input)

    # Fetch and return all posts from the search results
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        posts.append(item)
    
    return posts

def scrape_instagram_profile(profile_urls):
    # Initialize the ApifyClient with your API token
    client = ApifyClient(settings.apify_api_token)

    # Prepare the Actor input
    run_input = {
        "addParentData": False,
        "directUrls": profile_urls,
        "resultsType": "details", 
    }

    # Run the Actor and wait for it to finish
    run = client.actor("apify/instagram-scraper").call(run_input=run_input)

    # Fetch and print Actor results from the run's dataset (if there are any)
    results = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        results.append(format_ig_profile(item))
        
    return results

def remove_child_posts(apify_post):
    """Remove childPosts field from a post dictionary while preserving all other fields."""
    return {key: value for key, value in apify_post.items() if key != "childPosts"}

def format_ig_profile(apify_profile):
    profile = {}
    for key, value in apify_profile.items():
        if key == "latestPosts":
            profile["latestPosts"] = [remove_child_posts(post) for post in value]
        else:
            profile[key] = value

    return profile
