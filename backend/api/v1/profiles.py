from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from schemas.profile import ProfileCreate, ProfileUpdate, ProfileResponse
from services.profile_service import profile_service
from utils.auth import verify_clerk_token

router = APIRouter()

@router.get("/profiles", response_model=List[ProfileResponse])
async def get_profiles(user_claims: dict = Depends(verify_clerk_token)):
    user_id = user_claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    return await profile_service.get_profiles(user_id)

@router.post("/profiles", response_model=ProfileResponse)
async def create_profile(profile: ProfileCreate, user_claims: dict = Depends(verify_clerk_token)):
    user_id = user_claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    return await profile_service.create_profile(user_id, profile)

@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(profile_id: str, profile: ProfileUpdate, user_claims: dict = Depends(verify_clerk_token)):
    user_id = user_claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
    
    updated_profile = await profile_service.update_profile(user_id, profile_id, profile)
    if not updated_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return updated_profile

@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, user_claims: dict = Depends(verify_clerk_token)):
    user_id = user_claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")
        
    deleted = await profile_service.delete_profile(user_id, profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Profile not found")
