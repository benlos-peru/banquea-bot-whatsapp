import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from . import crud, schemas, database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])

@router.get("/", response_model=List[schemas.User])
def read_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1),
    db: Session = Depends(database.get_db)
):
    users = crud.get_users(db, skip=skip, limit=limit)
    return users

@router.post("/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(database.get_db)):
    db_user = crud.get_user_by_phone(db, phone_number=user.phone_number)
    if db_user:
        raise HTTPException(status_code=400, detail="Phone number already registered")
    return crud.create_user(db=db, user=user)

@router.get("/{user_id}", response_model=schemas.User)
def read_user(user_id: int, db: Session = Depends(database.get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user

@router.put("/{user_id}", response_model=schemas.User)
def update_user(
    user_id: int,
    user: schemas.UserUpdate,
    db: Session = Depends(database.get_db)
):
    db_user = crud.update_user(db=db, user_id=user_id, user=user)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Reschedule question job if schedule or phone changed
    from .scheduler import scheduler, schedule_next_question
    from .active_users import active_user_manager
    from .models import UserState
    job_id = f"question_confirmation_{db_user.id}"
    # Remove any existing job
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    # Schedule a new job only if user is active and subscribed
    if db_user.state == UserState.SUBSCRIBED and active_user_manager.is_active(db_user.phone_number):
        schedule_next_question(db_user, db)
    return db_user

@router.delete("/{user_id}")
def delete_user(user_id: int, db: Session = Depends(database.get_db)):
    success = crud.delete_user(db=db, user_id=user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    # Remove scheduled job for deleted user
    from .scheduler import scheduler
    job_id = f"question_confirmation_{user_id}"
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass
    return {"detail": "User deleted successfully"}

@router.post("/contact", response_model=dict)
async def contact_users(
    limit: int = Query(10, description="Maximum number of users to contact"),
    db: Session = Depends(database.get_db)
):
    """
    Trigger the contact process for uncontacted users.
    This endpoint will send initial welcome messages to users in UNCONTACTED state.
    
    Args:
        limit: Maximum number of users to contact in one batch
        db: Database session
        
    Returns:
        Dict with contact results
    """
    from .message_handler import whatsapp_client, handle_uncontacted_user
    from .models import UserState
    from .active_users import active_user_manager # Import active user manager
    import asyncio
    
    # Get users in UNCONTACTED state
    users = db.query(crud.models.User).filter(
        crud.models.User.state == UserState.UNCONTACTED
    ).limit(limit).all()
    
    if not users:
        return {"status": "no_users", "contacted": 0}
    
    success_count = 0
    failed_count = 0
    skipped_inactive = 0 # Counter for skipped inactive users
    results = []
    
    # Contact each user
    for user in users:
        # Check if user is active before contacting
        if not active_user_manager.is_active(user.phone_number):
            logger.info(f"Skipping contact for inactive user: {user.phone_number}")
            results.append({
                "phone_number": user.phone_number,
                "status": "skipped",
                "reason": "inactive_user"
            })
            skipped_inactive += 1
            continue # Skip to the next user
            
        try:
            # Use the handle_uncontacted_user method to manage user contact
            # Pass the user object directly
            contact_result = await handle_uncontacted_user(db, user, {})
            
            # handle_uncontacted_user now manages state changes internally
            # Check the result status
            if contact_result.get("status") == "success":
                 results.append({
                    "phone_number": user.phone_number,
                    "status": "success"
                })
                 success_count += 1
            else:
                results.append({
                    "phone_number": user.phone_number,
                    "status": "failed",
                    "reason": contact_result.get("reason", "unknown_error")
                })
                failed_count += 1
            
            # Small delay between users
            await asyncio.sleep(1) # Reduced delay slightly
            
        except Exception as e:
            # Rollback might not be needed if handle_uncontacted_user handles its own session/errors
            # db.rollback() 
            logger.error(f"Error contacting user {user.phone_number}: {str(e)}", exc_info=True)
            results.append({
                "phone_number": user.phone_number,
                "status": "error",
                "reason": str(e)
            })
            failed_count += 1
    
    return {
        "status": "completed",
        "total_processed": len(users),
        "contact_attempts": success_count + failed_count,
        "success": success_count,
        "failed": failed_count,
        "skipped_inactive": skipped_inactive,
        "results": results
    }
