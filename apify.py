from apify_client import ApifyClient
from config import settings
import os


def search_instagram_posts_by_keywords(keywords, limit=10):
    """
    Search for Instagram posts by keyword using hashtag search
    """
    # Initialize the ApifyClient with your API token
    client = ApifyClient(settings.apify_api_token)

    # Prepare the Actor input for keyword search
    run_input = {
        "hashtags": [''.join(c for c in keyword if c.isalpha()) for keyword in keywords],
        "keywordSearch": True,
        "resultsLimit": limit,
        "resultsType": "posts"
    }
    # print(run_input)

    # Run the Actor and wait for it to finish
    run = client.actor("apify/instagram-hashtag-scraper").call(run_input=run_input)

    # print(run)

    # Fetch and return all posts from the search results
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        posts.append(item)
    print(len(posts), "posts found!")
    return posts


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
    print(len(posts), "posts found!")
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


def search_linkedin_posts_by_keyword(keyword: str, limit: int = 10):
    """
    Search for LinkedIn posts by keyword using Apify LinkedIn Posts Search Scraper (No Cookies)
    Actor: apimaestro/linkedin-posts-search-scraper-no-cookies
    """
    client = ApifyClient(settings.apify_api_token)
    
    # Prepare the Actor input for keyword search
    run_input = {
        "keyword": keyword,
        "sort_type": "relevance",
        "page_number": 1,
        "limit": min(limit, 50),  # Max 50 per page according to API docs
        "date_filter": ""  # Empty means no date filter
    }
    
    # Run the Actor and wait for it to finish
    run = client.actor("apimaestro/linkedin-posts-search-scraper-no-cookies").call(run_input=run_input)
    
    # Fetch and return all posts from the search results
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        posts.append(item)
    
    return posts


def search_twitter_posts_by_keyword(keyword: str, limit: int = 10):
    """
    Search for Twitter/X posts by keyword using Apify Twitter Scraper PPR
    Actor: danek/twitter-scraper-ppr
    """
    client = ApifyClient(settings.apify_api_token)
    
    # Prepare the Actor input for keyword search
    run_input = {
        "query": keyword,
        "search_type": "Latest",
        "max_posts": limit
    }
    
    # Run the Actor and wait for it to finish
    run = client.actor("danek/twitter-scraper-ppr").call(run_input=run_input)
    
    # Fetch and format all posts from the search results
    posts = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        print("*"*100)
        print(item)
        print("*"*100)
        # Extract user info
        user_info = item.get("user_info", {})
        screen_name = item.get("screen_name") or user_info.get("screen_name", "")
        tweet_id = item.get("tweet_id", "")
        
        # Extract media images
        images = []
        media = item.get("media", {})
        if media and media.get("photo", []):
            for photo in media["photo"]:
                if photo.get("media_url_https"):
                    images.append(photo["media_url_https"])
        
        # Format the tweet data to match our expected structure
        formatted_post = {
            "id": tweet_id,
            "platform": "twitter",
            "text": item.get("text", ""),
            "author": {
                "name": user_info.get("name", ""),
                "username": screen_name,
                "profile_image_url": user_info.get("avatar", ""),
                "verified": user_info.get("verified", False),
                "bio": user_info.get("bio", ""),
                "location": user_info.get("location", "")
            },
            "engagement": {
                "likes": item.get("favorites", 0),
                "retweets": item.get("retweets", 0),
                "replies": item.get("replies", 0),
                "views": item.get("views", "0")
            },
            "created_at": item.get("created_at", ""),
            "url": f"https://twitter.com/{screen_name}/status/{tweet_id}" if screen_name and tweet_id else "",
            "images": images,
        }
        posts.append(formatted_post)
    
    print(len(posts), "Twitter posts found!")
    return posts
