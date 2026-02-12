from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi import UploadFile, File, Form
import httpx
from urllib.parse import urlparse
from pydantic import BaseModel
from typing import List, Optional
from config import settings
from main import (
    get_actions_for_keyword,
    get_creators,
    extract_post_context,
    generate_engaging_comment,
    identify_trending_topics,
)
from main import analyze_text_to_brief, transcribe_media_bytes, transcribe_from_url, SocialMediaBrief, get_related_instagram_posts, get_related_linkedin_posts, get_related_twitter_posts
import json
import asyncio

app = FastAPI(
    title=settings.app_name, 
    version=settings.app_version,
    debug=settings.debug
)

# Allow CORS for local development UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"]
    ,
    allow_headers=["*"]
)

print(settings.openai_api_key)

class ActionResponse(BaseModel):
    action: str
    url: str
    comment: Optional[str] = None
    caption: Optional[str] = None
    img_url: Optional[str] = None

class KeywordRequest(BaseModel):
    keyword: str

# Generic actions for unknown keywords
GENERIC_ACTIONS = [
    {
      "action": 'follow',
      "url": 'https://instagram.com/fitness_guru_official',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg'
    },
    {
      "action": 'like',
      "url": "https://www.instagram.com/p/C8X10w6Pd3X/",
      "caption": "Full video 🔗in b!0 AsoebiBar provides an Online One-Stop-Shop for Asoebi; which is traditional Afri...",
      "img_url": "https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg"
    },
    {
      "action": 'comment',
      "url": 'https://www.instagram.com/p/BaY6cwuglzg/',
      "comment": "Great content! Keep it up! 👏",
    },
    {
      "action": 'follow',
      "url": 'https://instagram.com/healthy_lifestyle_tips',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg',
    },
    {
      "action": 'like',
      "img_url": 'https://thesavvyimg.co.uk/wp-content/uploads/2020/06/uk-img-doctor-plab-mrcp-mrcs.jpg',
      "caption": "Excited to share my latest fitness journey update! 💪 Down 20lbs and feeling stronger than ever. Check out my workout tips and meal prep ideas below! #FitnessJourney #HealthyLifestyle",
      "url": 'https://www.instagram.com/p/cUQsS4EHgu/',
    },
]


@app.get("/")
async def root():
    return {"message": "Social Media Promotion API is running!"}

@app.post("/actions", response_model=List[ActionResponse])
async def get_actions(request: KeywordRequest):
    """
    Get a list of social media actions (follow, like, comment) for a given keyword
    """
    keyword = request.keyword.lower().strip()
    
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    try:
        # Generate real actions based on the keyword
        actions = await get_actions_for_keyword(keyword, max_posts=12)
        
        # If no actions found, return generic actions as fallback
        if not actions:
            return []
        
        return actions
        
    except Exception as e:
        # If there's an error, return generic actions as fallback
        print(f"Error getting actions for keyword '{keyword}': {str(e)}")
        return []

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is operational"}


class CreatorsRequest(BaseModel):
    keyword: str
    country: Optional[str] = None
    followers_count_gt: Optional[int] = None
    followers_count_lt: Optional[int] = None
    sort_by_emergence: Optional[bool] = False


@app.post("/creators")
async def get_creators_post_api(request: CreatorsRequest):
    """
    POST: Accepts JSON body with keyword, country and optional follower filters.
    If sort_by_emergence is True, calculates emergence scores and sorts by growth potential.
    """
    keyword = (request.keyword or "").strip()
    country = (request.country or "").strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    
    filters = {}
    if request.followers_count_gt is not None:
        filters["followers_count_gt"] = request.followers_count_gt
    if request.followers_count_lt is not None:
        filters["followers_count_lt"] = request.followers_count_lt
    if country:
        filters["country"] = country

    return await get_creators(keyword, filters, sort_by_emergence=request.sort_by_emergence or False)

@app.get("/proxy-image")
async def proxy_image(url: str):
    """
    Image proxy to bypass CDN CORS/CORP for profile pictures.
    Only allows known instagram/fb cdn hosts.
    """
    parsed = urlparse(url)
    allowed_hosts = (
        "instagram.com",
        "cdninstagram.com",
        "fbcdn.net",
    )
    if not any(host in parsed.netloc for host in allowed_hosts):
        raise HTTPException(status_code=400, detail="Host not allowed")

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.instagram.com/",
        }) as client:
            r = await client.get(url)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Failed to fetch image")
        content_type = r.headers.get("Content-Type", "image/jpeg")
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
        }
        return Response(content=r.content, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream error: {exc}")


class BlogpostRequest(BaseModel):
    text: str


class BlogpostBriefResponse(SocialMediaBrief):
    pass

demo_response = {
  "ad_targeting_topics": [
    "AI development",
    "JSON schema compliance",
    "OpenAI API features",
    "Structured data generation",
    "Model reliability enhancement"
  ],
  "hashtags": [
    "#DevDay2023",
    "#JSONMode",
    "#StructuredOutputs",
    "#OpenAIAPI",
    "#AIDevelopment"
  ],
  "micro_share_ideas": [
    "Discover how Structured Outputs enhance model reliability!",
    "JSON mode just got an upgrade – learn more today!",
    "Transform unstructured data effortlessly with Structured Outputs.",
    "Join us in celebrating the power of AI-driven data!",
    "Build reliable applications with our new API features."
  ],
  "keywords": [
    "OpenAI",
    "JSON mode",
    "Structured Outputs",
    "AI data generation",
    "developer tools"
  ]
}

@app.post("/analyze/blogpost", response_model=BlogpostBriefResponse)
async def analyze_blogpost(request: BlogpostRequest):
    # return demo_response
    text = (request.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text cannot be empty")
    brief = await analyze_text_to_brief(text)
    return brief


class VideoBriefResponse(SocialMediaBrief):
    transcript: Optional[str] = None


@app.post("/analyze/video", response_model=VideoBriefResponse)
async def analyze_video(
    url: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
):
    if not url and not file:
        raise HTTPException(status_code=400, detail="Provide either url or file")

    transcript = ""
    try:
        if url:
            transcript = await transcribe_from_url(url)
        else:
            content = await file.read()
            transcript = await transcribe_media_bytes(content, file.filename or "upload.mp4")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    print(transcript)
    if not transcript:
        raise HTTPException(status_code=422, detail="Empty transcript")

    brief = await analyze_text_to_brief(transcript)
    return VideoBriefResponse(**brief.model_dump(), transcript=transcript)


class RelatedPostsRequest(BaseModel):
    keywords: List[str]


@app.post("/related-posts/instagram")
async def related_instagram_posts(req: RelatedPostsRequest):
    # return []
    if not req.keywords:
        raise HTTPException(status_code=400, detail="keywords cannot be empty")

    try:
        # tasks = [get_related_instagram_posts(k) for k in req.keywords]
        # results = await asyncio.gather(*tasks, return_exceptions=True)
        results = await get_related_instagram_posts(req.keywords)

        return results
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch related posts: {str(e)}")

class GenerateCommentRequest(BaseModel):
    post: dict
    keywords: Optional[str] = None
    prior_post_text: Optional[str] = None
    custom_instructions: Optional[str] = None

class GenerateCommentResponse(BaseModel):
    comment: str


@app.post("/generate-comment", response_model=GenerateCommentResponse)
async def generate_comment(req: GenerateCommentRequest):
    try:
        context = extract_post_context(req.post)
        comment = await generate_engaging_comment(
            context,
            req.keywords,
            req.prior_post_text,
            req.custom_instructions,
        )
        return {"comment": comment.strip("\"").strip("\'")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate comment: {str(e)}")


@app.post("/related-posts/linkedin")
async def related_linkedin_posts(req: RelatedPostsRequest):
    """
    Get related LinkedIn posts for given keywords
    """
    # return []
    if not req.keywords:
        raise HTTPException(status_code=400, detail="keywords cannot be empty")

    try:
        tasks = [get_related_linkedin_posts(k) for k in req.keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        res = []
        for r in results:
            if isinstance(r, Exception):
                raise r

            res.extend(r)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch LinkedIn posts: {str(e)}")


@app.post("/related-posts/twitter")
async def related_twitter_posts(req: RelatedPostsRequest):
    """
    Get related Twitter/X posts for given keywords using Apify Twitter Scraper
    """
    # return []
    if not req.keywords:
        raise HTTPException(status_code=400, detail="keywords cannot be empty")

    try:
        tasks = [get_related_twitter_posts(k) for k in req.keywords]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        res = []
        for r in results:
            if isinstance(r, Exception):
                raise r

            res.extend(r)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Twitter posts: {str(e)}")


class TrendingTopicsRequest(BaseModel):
    niche_keywords: List[str]
    platforms: Optional[List[str]] = ["instagram", "linkedin", "twitter"]
    timeframe_hours: Optional[int] = 24


@app.post("/trending-topics")
async def get_trending_topics_endpoint(request: TrendingTopicsRequest):
    """
    Analyze trending topics in a specific niche across Instagram, LinkedIn, and Twitter using Apify
    """
    if not request.niche_keywords:
        raise HTTPException(status_code=400, detail="niche_keywords cannot be empty")
    
    try:
        result = await identify_trending_topics(
            request.niche_keywords,
            request.platforms or ["instagram", "linkedin", "twitter"],
            request.timeframe_hours or 24
        )
        return result
    except Exception as e:
        print(f"Error in trending topics: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to fetch trending topics: {str(e)}"
        )


