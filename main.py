from openai import AsyncOpenAI, OpenAI
from apify import search_instagram_posts_by_keyword, scrape_instagram_profile
import json
import asyncio
from config import settings
from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Any
import httpx
import os
import tempfile


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
    import base64

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
):
    """
    Generate an engaging comment for a post using OpenAI (async version)
    """
   
    keyword_prompt = f"- Search keyword(s): {keyword}" if keyword else ""
    prior_post_prompt = (
        f"- Our earlier post (for grounding; cite or draw from if relevant): {prior_post_text[:400]}..."
        if prior_post_text else ""
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

    Guidelines for the comment:
    1. Be specific and relevant; add a fresh data point, nuance, or micro-correction if needed.
    2. If the post makes a questionable claim, politely challenge it and offer a concise correction grounded in our earlier post when applicable.
    3. Use a natural, domain-appropriate, colloquial tone (no corporate vibe).
    4. 1–2 sentences max. Up to 1 relevant emoji max. No hashtags.
    5. Do not be salesy. Do not say things like "check our profile" or any explicit CTA.
    6. Avoid being overly glowy or simpish; aim for thoughtful and slightly provocative.
    7. Mention something concrete from the post (a stat, claim, or angle) so it feels tailored.
    8. something controversial or challenging to spark discussion.

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

async def get_creators(keyword, filters={}):
    """
    Get a list of creators for a given keyword and country
    """
    country = filters.get('country', '')
    posts_raw = search_instagram_posts_by_keyword(keyword)
    posts = []

    for post in posts_raw:
        posts.extend(post.get("topPosts", []))
    
    print(f"Found {len(posts)} posts")
    
    # Get all unique owners first
    owners = set()
    for post in posts:
        owners.add(post.get('ownerUsername', ''))

    owners_profiles = get_users_profiles(list(owners), with_related_profiles=False)

    for filter, value in filters.items():
        if filter == 'followers_count_gt':
            owners_profiles = {username: profile for username, profile in owners_profiles.items() if profile.get('followersCount', 0) >= value}
        elif filter == 'followers_count_lt':
            owners_profiles = {username: profile for username, profile in owners_profiles.items() if profile.get('followersCount', 0) <= value}

    return owners_profiles

async def get_related_posts(keyword):
    print("Finding posts for keyword:", keyword)
    posts_raw = await asyncio.to_thread(search_instagram_posts_by_keyword, keyword)

    posts = []
    for post in posts_raw:
        top_posts = post.get("topPosts", [])
        top_posts.sort(key=lambda x: x.get('likesCount', 0) + x.get('commentsCount', 0) + x.get('reshareCount', 0), reverse=True)
        posts.extend(top_posts[:10])

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
            "videoUrl", 
            "hashtags", 
            "likesCount",
            "commentsCount",
            "reshareCount",
            "timestamp",
            "images",
            "locationName",
            "isSponsored",
            "ownerFullName",
            "ownerUsername",
            "ownerId",
            "creator_details",
            ]:
            newpost[k] = v
    return newpost


async def get_today_love_msg_greeting():
    """
    Ask OpenAI to generate a short, affectionate text message for a girlfriend.
    The message should be creative and may naturally include today's day and date.
    """
    today_str = datetime.now().strftime("%A, %B %d, %Y")

    system_msg = (
        "You craft warm, genuine, and creative SMS-length love messages. "
        "Keep it personal, natural, and not cheesy. Use 1-2 sentences max. "
        "You may reference the provided day/date naturally. Use up to 2 emojis max."
    )

    user_msg = (
        f"Girlfriend's name: Ifem\n"
        f"Today: {today_str}\n"
        "Write a text reminding her I love her, in a heartfelt, modern tone."
        "You dont always have to say 'just wanted to remind you that I love you', be creative and natural"
    )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=120,
        temperature=0.85,
    )

    return response.choices[0].message.content.strip()


class SocialMediaBrief(BaseModel):
    """
    Structured output for social media briefing content
    """
    ad_targeting_topics: list[str] = Field(description="A list of topics that the ad should target")
    hashtags: list[str] = Field(description="A list of hashtags that the ad should use")
    micro_share_ideas: list[str] = Field(description="A list of micro share ideas")
    keywords: list[str] = Field(description="A list of keywords which are strong search terms we can use to find related posts")


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
