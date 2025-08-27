from openai import AsyncOpenAI
from apify import search_instagram_posts_by_keyword, scrape_instagram_profile
import json
import asyncio
from config import settings
from datetime import datetime


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

async def generate_engaging_comment(post_context, keyword):
    """
    Generate an engaging comment for a post using OpenAI (async version)
    """
    # Create a prompt that focuses on generating high-engagement comments
    prompt = f"""
    You are a social media engagement expert. Generate a comment for an Instagram post that will maximize engagement and encourage people to check out our profile. the comment should be from a 3rd party point of view since we are replying as a company 

    Post Context:
    - Caption: {post_context['caption'][:200]}...
    - Hashtags: {', '.join(post_context['hashtags'][:5])}
    - Owner: @{post_context['owner_username']}
    - Likes: {post_context['likes_count']}
    - Comments: {post_context['comments_count']}
    - Search keyword: {keyword}

    Guidelines for the comment:
    1. Be authentic and relevant to the post content
    2. Add value (Drop related tips or hint related to the topic)
    4. Show genuine interest in the content
    4. Use coloqual language in the domain 
    5. Say something specific in your comment 
    6. Use emojis appropriately but don't overdo it
    7. Keep it concise (1-2 sentences max)
    8. Don't use hashtags in the comment
    9. Avoid being salesy or promotional
    10. Don't be overly official of simpish
    11. Tone should not be too glowy and stiff

    


    Generate a comment that feels natural and would encourage the poster and others to engage with our profile:
    """

    messages = [
        {"role": "system", "content": "You are an expert at creating engaging, authentic social media comments that drive meaningful interactions and profile visits."},
        {"role": "user", "content": prompt}
    ]

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=100,
        temperature=0.5  # Add some creativity
    )

    # 3. Ask thoughtful questions, share insights, or give genuine compliments


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
