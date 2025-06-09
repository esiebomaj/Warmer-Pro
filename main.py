from openai import OpenAI
from apify import search_instagram_posts_by_keyword
import json
from config import settings

# Initialize OpenAI client
client = OpenAI(
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
        "images": post_data.get("images", []) + [post_data.get("displayUrl", None)]
    }
    return context

def generate_engaging_comment(post_context, keyword):
    """
    Generate an engaging comment for a post using OpenAI
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

    response = client.chat.completions.create(
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

def process_keyword_search(keyword, max_comments=20):
    """
    Main function to search for posts by keyword and generate comments
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
        
        # Process each post and generate comments
        generated_comments = []
        
        for i, post in enumerate(posts[:max_comments]):
            print(f"\n📱 Processing post {i+1}/{min(len(posts), max_comments)}")
            
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
                
                # Generate engaging comment
                comment = generate_engaging_comment(post_context, keyword)
                
                result = {
                    "post_url": post_context['post_url'],
                    "owner": post_context['owner_username'],
                    "owner_full_name": post_context['owner_full_name'],
                    "likes": post_context['likes_count'],
                    "comments": post_context['comments_count'],
                    "engagement_score": engagement_score,
                    "caption_preview": post_context['caption'][:100] + "..." if len(post_context['caption']) > 100 else post_context['caption'],
                    "generated_comment": comment,
                    "hashtags": post_context['hashtags'][:5]
                }
                
                generated_comments.append(result)
                
                print(f"💡 Generated comment: {comment}")
                print(f"🔗 Post URL: {post_context['post_url']}")
            else:
                print("⏭️  Skipping post (low engagement potential)")
        
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

def main():
    """
    Main function to run the social promotion script
    """
    print("🚀 Instagram Social Promotion Bot")
    print("=" * 50)

    keywords = ["African Startup", "Health and Fitness" ]
    # keywords = ["tourism", "resort", "African startup", "special economic zone", "remote working", "digital nomads"]
    # keywords = ["special economic zone"]

    # Process the keyword search and generate comments
    for keyword in keywords:
        results = process_keyword_search(keyword)
    
        # Save results to file
        if results:
            filename = f"./social_promotion_results_1/{keyword.replace(' ', '_')}.json"
            with open(filename, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n💾 Results saved to: {filename}")

if __name__ == "__main__":
    main()
