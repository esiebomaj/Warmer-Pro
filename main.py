from openai import AsyncOpenAI, OpenAI
from apify import (search_instagram_posts_by_keyword,
                    search_instagram_posts_by_keywords, 
                    scrape_instagram_profile, 
                    search_linkedin_posts_by_keyword, 
                    search_twitter_posts_by_keyword)
import json
import re
import asyncio
from config import settings
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
import httpx
import os
import tempfile
import base64
from collections import Counter



# Initialize OpenAI async client
client = AsyncOpenAI(
    api_key=settings.openai_api_key,
)

def extract_post_context(post_data):
    """
    Extract relevant context from a post for comment generation
    """
    context = {
        "caption": post_data.get("caption", ""),
        "hashtags": post_data.get("hashtags", []),
        "likes_count": post_data.get("likesCount", 0),
        "comments_count": post_data.get("commentsCount", 0),
        "owner_username": post_data.get("ownerUsername", ""),
        "owner_full_name": post_data.get("ownerFullName", ""),
        "post_url": post_data.get("url", ""),
        "images": post_data.get("images", []) + [post_data.get("displayUrl", None)],
        "display_url": post_data.get("displayUrl", None)
    }
    return context

async def get_image_content(images):
    """
    Downloads images from URLs, converts them to base64, and formats for OpenAI Vision.
    Returns: List of dicts with type/image_url for OpenAI.
    """
    img_content = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for image_url in images:
            try:
                resp = await client.get(image_url)
                resp.raise_for_status()
                b64 = base64.b64encode(resp.content).decode("utf-8")
                img_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                })
            except Exception as e:
                print(f"Error processing image {image_url}: {e}")
    return img_content



async def generate_engaging_comment(
    post_context,
    keyword: Optional[str] = None,
    prior_post_text: Optional[str] = None,
    custom_instructions: Optional[str] = None,
):
    """
    Generate an engaging comment for a post using OpenAI (async version)
    """
   
    keyword_prompt = f"- Search keyword(s): {keyword}" if keyword else ""
    prior_post_prompt = (
        f"- Our earlier post (for grounding; cite or draw from if relevant): {prior_post_text[:400]}..."
        if prior_post_text else ""
    )
    custom_instructions_prompt = (
        f"- Custom user instructions (honor these as long as they don't conflict with the guardrails): {custom_instructions.strip()}"
        if custom_instructions and custom_instructions.strip()
        else ""
    )

    prompt = f"""
    You are a social media engagement expert.
    Write an Instagram comment that sparks discussion and curiosity (not a CTA).
    The comment should be from a 3rd party point of view since we are replying as a company.

    Post Context:
    - Caption: {post_context['caption'][:240]}...
    - Hashtags: {', '.join(post_context['hashtags'][:5])}
    - Owner: @{post_context['owner_username']}
    - Likes: {post_context['likes_count']}
    - Comments: {post_context['comments_count']}
    {keyword_prompt}
    {prior_post_prompt}
    {custom_instructions_prompt}

    Guidelines for the comment:
    1. Be specific and relevant; add a fresh data point, nuance, or micro-correction if needed.
    2. If the post makes a questionable claim, politely challenge it and offer a concise correction grounded in our earlier post when applicable.
    3. Use a natural, domain-appropriate, colloquial tone (no corporate vibe).
    4. 1–2 sentences max. Up to 1 relevant emoji max. No hashtags.
    5. Do not be salesy. Do not say things like "check our profile" or any explicit CTA.
    6. Avoid being overly glowy or simpish; aim for thoughtful and slightly provocative.
    7. Mention something concrete from the post (a stat, claim, or angle) so it feels tailored.
    8. Something controversial or challenging to spark discussion when appropriate.
    9. If the user provided custom instructions, follow them faithfully unless they conflict with these guidelines.

    Return only the comment text.
    """

    system_msg = "You craft incisive, respectful comments that add value, correct gently when needed, and invite conversation without explicit CTAs."

    # Always include images when present (vision models will use them)
    image_urls = post_context.get("images") or []
 
    if image_urls:
        user_content = [{"type": "text", "text": prompt}] + await get_image_content(image_urls)
        
    else:
        user_content = prompt

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_content},
    ]

    import pprint

    pprint.pprint(messages)

    # Prefer a strong, vision-capable default; allow override via argument
    model_name = "gpt-4o-mini"


    response = await client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=120,
        temperature=0.65,
    )

    return response.choices[0].message.content.strip()
def analyze_post_engagement_potential(post_context):
    """
    Analyze if a post has good engagement potential
    """
    likes = post_context.get('likes_count', 0)
    comments = post_context.get('comments_count', 0)
    
    # Simple scoring system
    engagement_score = 0
    
    # Higher likes indicate popular content
    if likes > 1000:
        engagement_score += 3
    elif likes > 100:
        engagement_score += 2
    elif likes > 10:
        engagement_score += 1
    
    # Good comment-to-like ratio indicates engaging content
    if likes > 0:
        comment_ratio = comments / likes
        if comment_ratio > 0.05:  # 5% comment rate is very good
            engagement_score += 3
        elif comment_ratio > 0.02:  # 2% is good
            engagement_score += 2
        elif comment_ratio > 0.01:  # 1% is decent
            engagement_score += 1
    
    # Recent posts (we can't check timestamp, so assume all are recent)
    engagement_score += 1
    
    return engagement_score

def get_users_profiles(usernames, with_related_profiles=False):
    """
    Get the user profile from the usernames
    """
    res = {}
    profile_urls = [f"https://instagram.com/{username}" for username in usernames]
    profiles = scrape_instagram_profile(profile_urls)
    for profile in profiles:

        username = profile.get('username', '')
        # remove latestPosts from the profile
        if with_related_profiles:
            res[username] = {k:v for k,v in profile.items() if k not in ['latestPosts', 'latestIgtvVideos']}
        else:
            res[username] = {k:v for k,v in profile.items() if k not in ['latestPosts', 'latestIgtvVideos', 'relatedProfiles']}
    
    return res

def get_user_profile_pics(usernames):
    """
    Get the user profile pictures from the usernames
    """
    res = get_users_profiles(usernames)
    for username, profile in res.items():
        res[username] = profile.get('profilePicUrl', '')
    return res

async def process_single_post(post, keyword, profile_pics, post_index, total_posts):
    """
    Process a single post asynchronously
    """
    print(f"\n📱 Processing post {post_index + 1}/{total_posts}")
    
    # Extract context from the post
    post_context = extract_post_context(post)
    print(post_context)
    
    # Analyze engagement potential
    engagement_score = analyze_post_engagement_potential(post_context)
    
    print(f"👤 Owner: @{post_context['owner_username']}")
    print(f"❤️  Likes: {post_context['likes_count']}")
    print(f"💬 Comments: {post_context['comments_count']}")
    print(f"📊 Engagement Score: {engagement_score}/7")
    
    if engagement_score >= 1:  # Only comment on posts with decent engagement
        print("🎯 Generating comment...")
        
        # Generate engaging comment (async)
        comment = await generate_engaging_comment(post_context, keyword)
        
        result = {
            "post_url": post_context['post_url'],
            "owner": post_context['owner_username'],
            "owner_full_name": post_context['owner_full_name'],
            "owner_profile_pic": profile_pics.get(post_context['owner_username'], ''),
            "likes": post_context['likes_count'],
            "comments": post_context['comments_count'],
            "engagement_score": engagement_score,
            "caption_preview": post_context['caption'][:100] + "..." if len(post_context['caption']) > 100 else post_context['caption'],
            "generated_comment": comment,
            "hashtags": post_context['hashtags'][:5],
            "images": post_context['images']
        }
        
        print(f"💡 Generated comment: {comment}")
        print(f"🔗 Post URL: {post_context['post_url']}")
        return result
    else:
        print("⏭️  Skipping post (low engagement potential)")
        return None

async def process_keyword_search(keyword, max_comments=20):
    """
    Main function to search for posts by keyword and generate comments (async version)
    """
    print(f"🔍 Searching for posts with keyword: '{keyword}'")
    
    try:
        # Search for posts using the keyword
        posts = search_instagram_posts_by_keyword(keyword)
        posts_extracted = []

        for post in posts:
            posts_extracted.extend(post.get("topPosts", []))

        posts = posts_extracted
        
        if not posts:
            print("❌ No posts found for this keyword")
            return
        
        print(f"✅ Found {len(posts)} posts")
        
        # Get all unique owners first
        owners = set()
        for post in posts:
            owners.add(post.get('ownerUsername', ''))

        profile_pics = get_user_profile_pics(list(owners))
        
        # Process posts in parallel
        tasks = []
        posts_to_process = posts[:max_comments]
        
        for i, post in enumerate(posts_to_process):
            task = process_single_post(post, keyword, profile_pics, i, len(posts_to_process))
            tasks.append(task)
        
        # Execute all tasks concurrently
        print(f"\n🚀 Processing {len(tasks)} posts in parallel...")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        generated_comments = []
        for result in results:
            if result is not None and not isinstance(result, Exception):
                generated_comments.append(result)
            elif isinstance(result, Exception):
                print(f"❌ Error processing post: {str(result)}")

        # Summary
        print(f"\n📋 SUMMARY")
        print(f"🔍 Keyword searched: {keyword}")
        print(f"📱 Posts found: {len(posts)}")
        print(f"💬 Comments generated: {len(generated_comments)}")
        
        if generated_comments:
            print(f"\n🎯 TOP OPPORTUNITIES:")
            for i, comment_data in enumerate(generated_comments, 1):
                print(f"\n{i}. @{comment_data['owner']} ({comment_data['likes']} likes)")
                print(f"   Comment: {comment_data['generated_comment']}")
                print(f"   URL: {comment_data['post_url']}")
        
        return generated_comments
        
    except Exception as e:
        print(f"❌ Error processing keyword search: {str(e)}")
        return []


def generate_actions_from_posts(keyword, posts_data):
    """
    Convert post search results into actionable social media engagement tasks
    Format matches the GENERIC_ACTIONS structure from api.py
    """
    actions = []
    
    for post_data in posts_data:
        # Extract post image URL (prefer first image if available)
        post_img_url = post_data.get('display_url', None)

        
        # Extract profile picture URL
        username = post_data['owner']
        profile_img_url = post_data.get('owner_profile_pic', '')
        user_url = f"https://instagram.com/{username}"
        
        # Action 1: Follow the creator (one follow action per unique creator)
        creator_follow_action = {
            "action": "follow",
            "url": user_url,
            "img_url": profile_img_url  # Use profile picture for follow actions
        }
        
        # Check if we already have a follow action for this creator
        existing_follow = any(
            action.get("action") == "follow" and post_data['owner'] in action.get("url", "")
            for action in actions
        )
        
        if not existing_follow:
            actions.append(creator_follow_action)
        
        # Action 2: Like the post
        like_action = {
            "action": "like",
            "url": post_data['post_url'],
            "caption": post_data['caption_preview'],
            "img_url": post_img_url  # Use post image for like actions
        }
        actions.append(like_action)
        
        # Action 3: Comment on the post
        comment_action = {
            "action": "comment",
            "url": post_data['post_url'],
            "comment": post_data['generated_comment'],
            "caption": post_data['caption_preview'],  # Add caption for comment actions
            "img_url": post_img_url  # Use post image for comment actions
        }
        actions.append(comment_action)
    
    return actions


async def get_actions_for_keyword(keyword, max_posts=10):
    """
    Simplified function for API use - returns actions for a keyword without logging (async version)
    Returns actions in the same format as GENERIC_ACTIONS
    """
    try:
        # Get posts and generated comments for the keyword
        posts_data = await process_keyword_search(keyword, max_comments=max_posts)
        
        if not posts_data:
            return []
        
        # Convert posts data into actionable tasks
        actions = generate_actions_from_posts(keyword, posts_data)
        return actions
        
    except Exception as e:
        print(f"Error generating actions for keyword '{keyword}': {str(e)}")
        return []

async def get_creators(keyword, filters={}, sort_by_emergence: bool = False):
    """
    Get a list of creators for a given keyword and country.
    If sort_by_emergence is True, calculates emergence scores and returns sorted list.
    """
    country = filters.get('country', '')
    posts = search_instagram_posts_by_keywords([keyword])

    print(f"Found {len(posts)} posts")
    
    # Get all unique owners first
    owners = set()
    for post in posts:
        owners.add(post.get('ownerUsername', ''))

    owners_profiles = get_users_profiles(list(owners), with_related_profiles=False)

    for filter_key, value in filters.items():
        if filter_key == 'followers_count_gt':
            owners_profiles = {username: profile for username, profile in owners_profiles.items() if profile.get('followersCount', 0) >= value}
        elif filter_key == 'followers_count_lt':
            owners_profiles = {username: profile for username, profile in owners_profiles.items() if profile.get('followersCount', 0) <= value}

    if sort_by_emergence:
        # Calculate emergence scores and return as sorted list
        creators_with_scores = []
        for username, profile in owners_profiles.items():
            # Skip private accounts
            if profile.get('private', False):
                continue
            
            score_data = calculate_emergence_score(profile, posts)
            enriched_profile = {**profile, **score_data}
            creators_with_scores.append(enriched_profile)
        
        # Sort by emergence score (highest first)
        creators_with_scores.sort(key=lambda x: x.get('emergence_score', 0), reverse=True)
        return creators_with_scores
    
    return owners_profiles


def calculate_emergence_score(profile: dict, posts: list) -> dict:
    """
    Calculate an emergence/growth potential score for a creator.
    Higher scores indicate creators likely to grow/go viral soon.
    
    Factors considered:
    - Engagement rate (likes + comments per post relative to followers)
    - Follower-to-following ratio (indicates organic growth)
    - Posting consistency (active creators grow faster)
    - Sweet spot follower range (1K-100K = emerging)
    """
    followers = profile.get('followersCount', 0)
    following = profile.get('followsCount', 1)  # Avoid division by zero
    posts_count = profile.get('postsCount', 0)
    
    # Get engagement from recent posts by this creator
    creator_posts = [p for p in posts if p.get('ownerUsername') == profile.get('username')]
    
    total_likes = sum(p.get('likesCount', 0) for p in creator_posts)
    total_comments = sum(p.get('commentsCount', 0) for p in creator_posts)
    post_sample_size = len(creator_posts) or 1
    
    avg_likes = total_likes / post_sample_size
    avg_comments = total_comments / post_sample_size
    
    # 1. Engagement Rate Score (0-35 points)
    # Great engagement rate is 3-6%+, good is 1-3%
    if followers > 0:
        engagement_rate = ((avg_likes + avg_comments) / followers) * 100
    else:
        engagement_rate = 0
    
    if engagement_rate >= 6:
        engagement_score = 35
    elif engagement_rate >= 3:
        engagement_score = 28
    elif engagement_rate >= 1.5:
        engagement_score = 20
    elif engagement_rate >= 0.5:
        engagement_score = 10
    else:
        engagement_score = 3
    
    # 2. Follower-to-Following Ratio Score (0-25 points)
    # High ratio indicates organic growth, people follow without follow-back
    ff_ratio = followers / max(following, 1)
    
    if ff_ratio >= 10:
        ff_score = 25
    elif ff_ratio >= 5:
        ff_score = 20
    elif ff_ratio >= 2:
        ff_score = 15
    elif ff_ratio >= 1:
        ff_score = 10
    else:
        ff_score = 5
    
    # 3. Sweet Spot Follower Range Score (0-20 points)
    # Emerging creators typically have 1K-100K followers
    if 5000 <= followers <= 50000:
        size_score = 20  # Prime emerging range
    elif 1000 <= followers < 5000:
        size_score = 18  # Micro-influencer, high potential
    elif 50000 < followers <= 100000:
        size_score = 15  # Still emerging
    elif 500 <= followers < 1000:
        size_score = 12  # Very early stage
    elif 100000 < followers <= 500000:
        size_score = 8   # Established but not mega
    else:
        size_score = 3   # Either too small or already big
    
    # 4. Activity/Consistency Score (0-20 points)
    # More posts = more active creator
    if posts_count >= 200:
        activity_score = 20
    elif posts_count >= 100:
        activity_score = 16
    elif posts_count >= 50:
        activity_score = 12
    elif posts_count >= 20:
        activity_score = 8
    else:
        activity_score = 4
    
    # Calculate total score
    total_score = engagement_score + ff_score + size_score + activity_score
    
    return {
        "emergence_score": total_score,
        "engagement_rate": round(engagement_rate, 2),
        "ff_ratio": round(ff_ratio, 2),
        "avg_likes": round(avg_likes, 1),
        "avg_comments": round(avg_comments, 1),
    }


async def get_related_instagram_posts(keywords):
    print("Finding posts for keywords:", keywords)
    posts = await asyncio.to_thread(search_instagram_posts_by_keywords, keywords)

    owners = {post.get('ownerUsername', '') for post in posts}
    creator_profiles = await asyncio.to_thread(get_users_profiles, list(owners), False)

    for post in posts:
        username = post.get('ownerUsername', '')
        creator = creator_profiles.get(username, {})
        post["creator_details"] = creator
        post = formatRelatedPosts(post)

    print(f"Returning {len(posts)} posts")
    return posts


def formatRelatedPosts(post):
    """
    Format the related posts
    """
    newpost = {}
    for k, v in post.items():
        if k in [
            "inputUrl", 
            "type", 
            "caption", 
            "url", 
            "displayUrl", 
                # "videoUrl", 
            "hashtags", 
            "likesCount",
            "commentsCount",
                # "reshareCount",
            "timestamp",
            "images",
                # "locationName",
            "isSponsored",
            "ownerFullName",
            "ownerUsername",
            "ownerId",
            "creator_details",
            ]:
            newpost[k] = v
    return newpost


async def get_related_linkedin_posts(keyword):
    """
    Get related LinkedIn posts for a given keyword
    """
    print(f"Finding LinkedIn posts for keyword: {keyword}")
    # return []
    posts = await asyncio.to_thread(search_linkedin_posts_by_keyword, keyword, limit=10)
    print(f"Returning {len(posts)} LinkedIn posts")
    return posts
 

async def get_related_twitter_posts(keyword):
    """
    Get related Twitter/X posts for a given keyword using Apify Twitter Scraper
    """
    print(f"Finding Twitter posts for keyword: {keyword}")
    posts = await asyncio.to_thread(search_twitter_posts_by_keyword, keyword, limit=10)
    print(f"Returning {len(posts)} Twitter posts")
    return posts


class SocialMediaBrief(BaseModel):
    """
    Structured output for social media briefing content
    """
    ad_targeting_topics: List[str] = Field(description="A list of topics that the ad should target")
    hashtags: List[str] = Field(description="A list of hashtags that the ad should use")
    micro_share_ideas: List[str] = Field(description="A list of micro share ideas")
    keywords: List[str] = Field(description="A list of keywords which are strong search terms we can use to find related posts")


async def analyze_text_to_brief(text: str) -> SocialMediaBrief:
    """
    Use OpenAI to extract structured briefing content from a blog post or transcript.
    Returns a validated SocialMediaBrief.
    """
    print(f"Analyzing text to brief: {text[:8000]}")
    system_msg = (
        "You are a senior social strategist. Read the provided content and produce "
        "concise, actionable outputs for a marketing team."
    )

    user_msg = (
        "Analyze the following content and return ONLY a JSON object with these keys: "
        "ad_targeting_topics, hashtags, micro_share_ideas, keywords.\n\n"
        "Rules:\n"
        "- Each value must be an array of strings.\n"
        "- Prefer concrete, specific phrases (not generic).\n"
        "- hashtags should include the leading # and be platform-appropriate.\n"
        "- micro_share_ideas should be short bite-sized hooks or talking points (1 line each).\n"
        "- keywords should be 5 strong search terms we can use to find related posts.\n"
        "- Aim for 5-10 items for each list when content allows.\n\n"
        f"Content:\n{text[:8000]}"
    )
    response = await client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=1000,
        temperature=0.85,
        response_format=SocialMediaBrief,
    )

    resp_mgs = response.choices[0].message

    if resp_mgs.parsed:
        return resp_mgs.parsed

    print(resp_mgs.refusal)
    return None


async def transcribe_media_bytes(file_bytes: bytes, filename: str) -> str:
    """
    Transcribe audio/video bytes to text using OpenAI transcription.
    Supports common audio and video formats (e.g., mp3, m4a, wav, mp4, mov).
    """
    suffix = os.path.splitext(filename or "")[1] or ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcription = await client.audio.transcriptions.create(
                model="gpt-4o-transcribe",
                file=f,
            )
        text = getattr(transcription, "text", None)
        if not text and hasattr(transcription, "to_dict"):
            text = transcription.to_dict().get("text", "")
        return text or ""
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass


async def transcribe_from_url(url: str) -> str:
    """
    Download media from URL and transcribe.
    """
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client_http:
        r = await client_http.get(url)
        r.raise_for_status()
        content = r.content
    print(content)
    # Derive filename from URL path
    parsed_name = url.split("?")[0].rstrip("/").split("/")[-1] or "media.mp4"
    return await transcribe_media_bytes(content, parsed_name)

def calculate_trend_score(posts: List[Dict], timeframe_hours: int = 24) -> float:
    """
    Calculate a trending score based on:
    - Engagement velocity (likes/comments per hour)
    - Number of posts in timeframe
    - Engagement rate
    """
    if not posts:
        return 0.0
    
    recent_posts = []
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=timeframe_hours)
    
    for post in posts:
        # Try different timestamp fields
        timestamp_str = post.get('timestamp') or post.get('created_at') or post.get('createTime')
        if timestamp_str:
            try:
                # Handle Unix timestamp (TikTok)
                if isinstance(timestamp_str, (int, float)):
                    post_time = datetime.fromtimestamp(timestamp_str)
                else:
                    # Handle ISO format (Instagram)
                    post_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                if post_time >= cutoff:
                    recent_posts.append(post)
            except:
                # If parsing fails, include the post
                recent_posts.append(post)
        else:
            # If no timestamp, assume it's recent
            recent_posts.append(post)
    
    if not recent_posts:
        return 0.0
    
    # Calculate metrics
    total_engagement = 0
    total_views = 0
    
    for post in recent_posts:
        # Platform detection and engagement calculation
        platform = post.get('platform', '')
        
        if platform == 'twitter' or 'engagement' in post:
            # Twitter
            engagement = post.get('engagement', {})
            likes = engagement.get('likes', 0)
            retweets = engagement.get('retweets', 0)
            replies = engagement.get('replies', 0)
            total_engagement += likes + (retweets * 2) + replies
            total_views += max(likes * 15, 100)  # Estimate views from likes
            
        elif 'numLikes' in post or 'reactionCount' in post:
            # LinkedIn
            reactions = post.get('numLikes', 0) or post.get('reactionCount', 0)
            comments = post.get('numComments', 0) or post.get('commentCount', 0)
            shares = post.get('numShares', 0) or post.get('shareCount', 0)
            total_engagement += reactions + comments + (shares * 2)
            total_views += max(reactions * 20, 100)  # Estimate views from reactions
            
        else:
            # Instagram
            likes = post.get('likesCount', 0) or post.get('likes', 0)
            comments = post.get('commentsCount', 0) or post.get('comments', 0)
            total_engagement += likes + comments
            total_views += max(likes * 10, 100)  # Estimate views from likes
    
    engagement_rate = (total_engagement / total_views * 100) if total_views > 0 else 0
    
    # Velocity: engagement per hour
    velocity = total_engagement / timeframe_hours if timeframe_hours > 0 else 0
    
    # Post frequency score
    frequency_score = len(recent_posts) * 10
    
    # Combined score (weighted)
    trend_score = (
        velocity * 0.4 +           # 40% weight on velocity
        engagement_rate * 0.3 +     # 30% weight on engagement rate
        frequency_score * 0.3       # 30% weight on post frequency
    )
    
    return round(trend_score, 2)


async def fetch_niche_posts(
    niche_keywords: List[str],
    platforms: List[str] = ["instagram", "linkedin", "twitter"],
) -> List[Dict]:
    """
    Fetch posts from all selected platforms for given keywords.
    Tags each post with _platform so downstream analysis knows the source.
    Returns a single flat list of posts.
    """
    all_posts = []
    
    # 1. Instagram
    if "instagram" in platforms:
        print(f"📸 Fetching Instagram posts for {len(niche_keywords)} keywords...")
        for keyword in niche_keywords:
            try:
                posts = await asyncio.to_thread(
                    search_instagram_posts_by_keywords,
                    [keyword],
                    limit=50
                )
                for post in posts:
                    post['_platform'] = 'instagram'
                    all_posts.append(post)
            except Exception as e:
                print(f"⚠️  Error fetching Instagram keyword '{keyword}': {e}")
    
    # 2. LinkedIn
    if "linkedin" in platforms:
        print(f"💼 Fetching LinkedIn posts for {len(niche_keywords)} keywords...")
        for keyword in niche_keywords:
            try:
                posts = await asyncio.to_thread(
                    search_linkedin_posts_by_keyword,
                    keyword,
                    limit=50
                )
                for post in posts:
                    post['_platform'] = 'linkedin'
                    all_posts.append(post)
            except Exception as e:
                print(f"⚠️  Error fetching LinkedIn keyword '{keyword}': {e}")
    
    # 3. Twitter
    if "twitter" in platforms:
        print(f"🐦 Fetching Twitter posts for {len(niche_keywords)} keywords...")
        for keyword in niche_keywords:
            try:
                posts = await asyncio.to_thread(
                    search_twitter_posts_by_keyword,
                    keyword,
                    limit=50
                )
                for post in posts:
                    post['_platform'] = 'twitter'
                    all_posts.append(post)
            except Exception as e:
                print(f"⚠️  Error fetching Twitter keyword '{keyword}': {e}")
    
    print(f"📦 Total posts fetched: {len(all_posts)}")
    return all_posts


def analyze_hashtags_from_posts(
    all_posts: List[Dict],
    timeframe_hours: int = 24
) -> Dict:
    """
    Extract and score trending hashtags from already-fetched posts.
    Returns the hashtag trending results dict.
    """
    all_hashtag_data = {}
    
    for post in all_posts:
        platform = post.get('_platform', 'unknown')
        
        # Extract hashtags depending on platform
        if platform == 'instagram':
            hashtags = post.get('hashtags', [])
        else:
            text = post.get('text', '') or post.get('commentary', '') or ''
            hashtags = re.findall(r'#(\w+)', text)
        
        for tag in hashtags:
            tag_clean = tag.lower().strip('#')
            
            if tag_clean not in all_hashtag_data:
                all_hashtag_data[tag_clean] = {
                    'posts': [],
                    'platforms': set(),
                    'total_engagement': 0,
                    'is_official_trend': False
                }
            
            all_hashtag_data[tag_clean]['posts'].append(post)
            all_hashtag_data[tag_clean]['platforms'].add(platform)
            
            # Calculate engagement per platform
            if platform == 'instagram':
                all_hashtag_data[tag_clean]['total_engagement'] += (
                    (post.get('likesCount', 0) or 0) +
                    (post.get('commentsCount', 0) or 0)
                )
            elif platform == 'linkedin':
                reactions = post.get('numLikes', 0) or post.get('reactionCount', 0) or 0
                comments = post.get('numComments', 0) or post.get('commentCount', 0) or 0
                shares = post.get('numShares', 0) or post.get('shareCount', 0) or 0
                all_hashtag_data[tag_clean]['total_engagement'] += reactions + comments + (shares * 2)
            elif platform == 'twitter':
                engagement = post.get('engagement', {})
                likes = engagement.get('likes', 0) or 0
                retweets = engagement.get('retweets', 0) or 0
                replies = engagement.get('replies', 0) or 0
                all_hashtag_data[tag_clean]['total_engagement'] += likes + (retweets * 2) + replies
    
    # Calculate trend scores
    print("📊 Calculating hashtag trend scores...")
    trending_topics = []
    
    for hashtag, data in all_hashtag_data.items():
        if data['posts']:
            trend_score = calculate_trend_score(data['posts'], timeframe_hours)
        else:
            trend_score = 0
        
        # Boost score if trending on multiple platforms
        platform_multiplier = len(data['platforms']) * 1.5
        trend_score *= platform_multiplier
        
        if trend_score > 5:
            recent_post_count = len([p for p in data['posts'] if is_recent_post(p, timeframe_hours)])
            
            trending_topics.append({
                'topic': f"#{hashtag}",
                'trend_score': round(trend_score, 2),
                'platforms': list(data['platforms']),
                'post_count': len(data['posts']),
                'total_engagement': data['total_engagement'],
                'sample_posts': data['posts'][:5],
                'velocity': f"+{recent_post_count} posts/{timeframe_hours}h",
            })
    
    trending_topics.sort(key=lambda x: x['trend_score'], reverse=True)
    
    # Summary statistics
    platform_breakdown = Counter()
    total_posts = 0
    total_engagement = 0
    
    for topic in trending_topics:
        for platform in topic['platforms']:
            platform_breakdown[platform] += 1
        total_posts += topic['post_count']
        total_engagement += topic['total_engagement']
    
    return {
        'trending_topics': trending_topics[:20],
        'summary': {
            'total_trending_topics': len(trending_topics),
            'total_posts_analyzed': total_posts,
            'total_engagement': total_engagement,
            'platform_breakdown': dict(platform_breakdown),
        }
    }


async def identify_trending_topics(
    niche_keywords: List[str],
    platforms: List[str] = ["instagram", "linkedin", "twitter"],
    timeframe_hours: int = 24
) -> Dict:
    """
    Identify trending topics in your niche across Instagram, LinkedIn, and Twitter.
    Fetches posts ONCE, then runs two analyses in parallel:
      1. Hashtag extraction and scoring
      2. Conversation clustering via OpenAI
    """
    # Step 1: Fetch all posts once
    all_posts = await fetch_niche_posts(niche_keywords, platforms)
    
    # Step 2: Run both analyses on the same data
    hashtag_results = analyze_hashtags_from_posts(all_posts, timeframe_hours)
    conversation_results = await analyze_conversations_from_posts(all_posts, niche_keywords)
    
    return {
        'trending_topics': hashtag_results['trending_topics'],
        'conversations': conversation_results,
        'summary': {
            **hashtag_results['summary'],
            'niche_keywords': niche_keywords,
            'platforms_analyzed': platforms,
            'top_trend': hashtag_results['trending_topics'][0] if hashtag_results['trending_topics'] else None,
        }
    }


class SampleQuote(BaseModel):
    """A sample quote with the post numbers it came from"""
    quote: str = Field(description="A quote from the posts that represent this topic")
    post_numbers: List[int] = Field(description="The POST numbers (e.g. [3, 17]) of posts that discuss this specific point")


class ConversationCluster(BaseModel):
    """A trending conversation topic extracted from post text"""
    topic: str = Field(description="Short label for this conversation cluster, 3-6 words")
    description: str = Field(description="One sentence explaining what people are saying about this topic")
    related_post_numbers: List[int] = Field(description="All POST numbers that discuss this topic")
    sentiment: str = Field(description="Overall sentiment: positive, negative, mixed, or neutral")
    sample_quotes: List[SampleQuote] = Field(description="2-3 short direct quotes from the posts that represent this topic")
    subtopics: List[str] = Field(description="2-4 more specific angles within this topic")


class TrendingConversations(BaseModel):
    """Structured output for trending conversation clusters"""
    clusters: List[ConversationCluster]


async def analyze_conversations_from_posts(
    all_posts: List[Dict],
    niche_keywords: List[str],
) -> Dict:
    """
    Analyze actual post text to find trending conversation topics using OpenAI.
    Takes already-fetched posts (no extra Apify calls).
    """
    if not all_posts:
        return {'clusters': [], 'total_posts_analyzed': 0, 'post_index': []}

    # Build post text entries with engagement, platform info, and URL
    post_entries = []
    for post in all_posts:
        platform = post.get('_platform', 'unknown')

        # Extract text, engagement, and URL depending on platform
        if platform == 'instagram':
            text = post.get('caption', '') or ''
            engagement = (post.get('likesCount', 0) or 0) + (post.get('commentsCount', 0) or 0)
            url = post.get('url', '') or post.get('shortCode', '')
            if url and not url.startswith('http'):
                url = f"https://www.instagram.com/p/{url}/"
        elif platform == 'linkedin':
            text = post.get('text', '') or post.get('commentary', '') or ''
            reactions = post.get('numLikes', 0) or post.get('reactionCount', 0) or 0
            comments = post.get('numComments', 0) or post.get('commentCount', 0) or 0
            engagement = reactions + comments
            url = post.get('url', '') or post.get('postUrl', '') or ''
        elif platform == 'twitter':
            text = post.get('text', '') or ''
            eng = post.get('engagement', {})
            engagement = (eng.get('likes', 0) or 0) + (eng.get('retweets', 0) or 0)
            url = post.get('url', '') or post.get('tweetUrl', '') or ''
        else:
            text = post.get('caption', '') or post.get('text', '') or ''
            engagement = 0
            url = post.get('url', '') or ''

        if text and len(text.strip()) > 20:
            post_entries.append({
                'text': text[:500],
                'platform': platform,
                'engagement': engagement,
                'url': url or '',
            })

    if not post_entries:
        return {'clusters': [], 'total_posts_analyzed': 0, 'post_index': []}

    # Sort by engagement so we analyze the most impactful posts first
    post_entries.sort(key=lambda x: x['engagement'], reverse=True)

    # Take top 100 posts to stay within token limits
    top_posts = post_entries[:100]

    # Build a numbered post index (for resolving post numbers → URLs later)
    post_index = []
    for i, p in enumerate(top_posts, start=1):
        post_index.append({
            'post_number': i,
            'platform': p['platform'],
            'url': p['url'],
        })

    # Build the numbered text block for OpenAI
    combined_text = ""
    for i, p in enumerate(top_posts, start=1):
        combined_text += f"POST {i} [{p['platform'].upper()}] (engagement: {p['engagement']}): {p['text']}\n---\n"

    print(f"💬 Analyzing {len(top_posts)} posts for conversation clusters...")

    try:
        response = await client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a social media trend analyst. Analyze the following numbered posts from "
                        "Instagram, LinkedIn, and Twitter to identify trending conversation topics "
                        "and themes. Group similar posts into clusters. Focus on what people are "
                        "ACTUALLY talking about — the substance of their posts, not just hashtags.\n\n"
                        "IMPORTANT RULES:\n"
                        "- Each post is numbered (POST 1, POST 2, etc.). You MUST reference these numbers.\n"
                        # "- For sample_quotes: Copy text EXACTLY and VERBATIM from the posts. Do NOT paraphrase or invent quotes.\n"
                        "- For related_post_numbers: List ALL post numbers that discuss this topic.\n"
                        "- For each sample_quote: Include the post_numbers array with the POST number(s) the quote comes from.\n"
                        "- Only use information from the provided posts. Do NOT invent or hallucinate content.\n"
                        "- Rank clusters by how frequently topics appear and how much engagement they get.\n"
                        "- Return 5-10 clusters."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Analyze these {len(top_posts)} numbered social media posts about "
                        f"'{', '.join(niche_keywords)}' and identify the top trending conversation "
                        f"topics.\n\n"
                        f"For each cluster, provide:\n"
                        f"- topic: A short label (3-6 words)\n"
                        f"- description: One sentence about what people are saying\n"
                        f"- related_post_numbers: List of POST numbers that discuss this topic\n"
                        f"- sentiment: positive, negative, mixed, or neutral\n"
                        f"- sample_quotes: 2-3 objects, each with a 'quote' (copied VERBATIM from a post) "
                        f"and 'post_numbers' (the POST numbers the quote comes from)\n"
                        f"- subtopics: 2-4 specific angles within this topic\n\n"
                        f"Posts:\n{combined_text}"
                    )
                }
            ],
            max_tokens=3000,
            temperature=0.4,
            response_format=TrendingConversations,
        )

        parsed = response.choices[0].message.parsed

        if not parsed:
            print("⚠️  OpenAI returned no parsed conversations")
            return {'clusters': [], 'total_posts_analyzed': len(post_entries), 'post_index': post_index}

        # Build a lookup from post number → URL
        post_url_lookup = {p['post_number']: p['url'] for p in post_index}

        clusters_data = []
        for cluster in parsed.clusters:
            # Resolve post numbers to URLs for each sample quote
            resolved_quotes = []
            for sq in cluster.sample_quotes:
                resolved_posts = []
                for pn in sq.post_numbers:
                    url = post_url_lookup.get(pn, '')
                    if url:
                        resolved_posts.append({'post_number': pn, 'url': url})
                resolved_quotes.append({
                    'quote': sq.quote,
                    'post_numbers': sq.post_numbers,
                    'posts': resolved_posts,
                })

            # Resolve related_post_numbers to URLs
            related_posts = []
            for pn in cluster.related_post_numbers:
                url = post_url_lookup.get(pn, '')
                if url:
                    related_posts.append({'post_number': pn, 'url': url})

            clusters_data.append({
                'topic': cluster.topic,
                'description': cluster.description,
                'mention_count': len(cluster.related_post_numbers),
                'sentiment': cluster.sentiment,
                'sample_quotes': resolved_quotes,
                'subtopics': cluster.subtopics,
                'related_posts': related_posts,
            })

        print(f"✅ Found {len(clusters_data)} conversation clusters")
        return {
            'clusters': clusters_data,
            'total_posts_analyzed': len(post_entries),
            'post_index': post_index,
        }

    except Exception as e:
        print(f"⚠️  Error analyzing conversations: {e}")
        import traceback
        traceback.print_exc()
        return {'clusters': [], 'total_posts_analyzed': len(post_entries), 'post_index': post_index}


def is_recent_post(post: Dict, hours: int) -> bool:
    """Check if post is within the recent timeframe"""
    try:
        timestamp_str = post.get('timestamp') or post.get('created_at') or post.get('createTime')
        if not timestamp_str:
            return True
        
        if isinstance(timestamp_str, (int, float)):
            post_time = datetime.fromtimestamp(timestamp_str)
        else:
            post_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return post_time >= cutoff
    except:
        return True


async def main():
    """
    Main function to run the social promotion script (async version)
    """
    print("🚀 Instagram Social Promotion Bot")
    print("=" * 50)

    keywords = ["African Startup", "Health and Fitness" ]
    # keywords = ["tourism", "resort", "African startup", "special economic zone", "remote working", "digital nomads"]
    # keywords = ["special economic zone"]

    # Process all keywords concurrently
    tasks = []
    for keyword in keywords:
        tasks.append(process_keyword_search(keyword))
    
    print(f"\n🚀 Processing {len(keywords)} keywords in parallel...")
    all_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Save results to files
    for keyword, results in zip(keywords, all_results):
        if results and not isinstance(results, Exception):
            filename = f"./social_promotion_results_1/{keyword.replace(' ', '_')}.json"
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n💾 Results for '{keyword}' saved to: {filename}")
        elif isinstance(results, Exception):
            print(f"❌ Error processing keyword '{keyword}': {str(results)}")

if __name__ == "__main__":
    asyncio.run(main())
