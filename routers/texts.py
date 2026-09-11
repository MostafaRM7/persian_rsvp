from typing import List
from fastapi import APIRouter, Depends, HTTPException, status

from auth import get_current_user
from models import SavedText, User
from schemas import SavedTextCreate, SavedTextOut, SavedTextUpdate

router = APIRouter(prefix="/api/texts", tags=["texts"])


@router.get("", response_model=List[SavedTextOut])
async def list_texts(current_user: User = Depends(get_current_user)):
    texts = await SavedText.filter(user=current_user).order_by("-updated_at")
    return [SavedTextOut.model_validate(t) for t in texts]


@router.post("", response_model=SavedTextOut, status_code=status.HTTP_201_CREATED)
async def create_text(text_data: SavedTextCreate, current_user: User = Depends(get_current_user)):
    text = await SavedText.create(
        user=current_user,
        title=text_data.title,
        content=text_data.content,
        wpm=text_data.wpm or current_user.preferred_wpm,
    )
    return SavedTextOut.model_validate(text)


@router.get("/{text_id}", response_model=SavedTextOut)
async def get_text(text_id: int, current_user: User = Depends(get_current_user)):
    text = await SavedText.get_or_none(id=text_id, user=current_user)
    if not text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="متن مورد نظر پیدا نشد.")
    return SavedTextOut.model_validate(text)


@router.put("/{text_id}", response_model=SavedTextOut)
async def update_text(
    text_id: int,
    text_data: SavedTextUpdate,
    current_user: User = Depends(get_current_user),
):
    text = await SavedText.get_or_none(id=text_id, user=current_user)
    if not text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="متن مورد نظر پیدا نشد.")

    if text_data.title is not None:
        text.title = text_data.title
    if text_data.content is not None:
        text.content = text_data.content
    if text_data.last_position is not None:
        text.last_position = text_data.last_position
    if text_data.wpm is not None:
        text.wpm = text_data.wpm

    await text.save()
    return SavedTextOut.model_validate(text)


@router.delete("/{text_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_text(text_id: int, current_user: User = Depends(get_current_user)):
    text = await SavedText.get_or_none(id=text_id, user=current_user)
    if not text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="متن مورد نظر پیدا نشد.")
    await text.delete()
