from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from config import settings
from main import process_keyword_search, get_actions_for_keyword

app = FastAPI(
    title=settings.app_name, 
    version=settings.app_version,
    debug=settings.debug
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
        actions = get_actions_for_keyword(keyword, max_posts=8)
        
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
