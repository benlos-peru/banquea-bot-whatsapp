import pandas as pd
from pathlib import Path
from typing import Dict, List
import logging
import httpx

logger = logging.getLogger(__name__)

class QuestionManager:
    def __init__(self):
        self.questions_df = None
        self.correct_answers_df = None
        self.incorrect_answers_df = None
        self._load_questions()

    def _load_questions(self):
        """Fetch all questions from external API into memory"""
        try:
            # Query external API endpoint
            response = httpx.get("https://enarm.pe/api/statistics/qanda", timeout=10)
            response.raise_for_status()
            payload = response.json()
            data = payload.get('data', []) or []
            # Build DataFrame
            df = pd.DataFrame(data)
            # Normalize column names
            df = df.rename(columns={'id':'question_id', 'pregunta':'question_text', 'respuesta':'answer_text'})
            # Store question texts (unique)
            self.questions_df = df[['question_id','question_text']].drop_duplicates().reset_index(drop=True)
            # Correct answers where alternativas==1
            self.correct_answers_df = df[df['alternativas']==1][['question_id','answer_text']].reset_index(drop=True)
            # Incorrect answers where alternativas==0
            self.incorrect_answers_df = df[df['alternativas']==0][['question_id','answer_text']].reset_index(drop=True)
            # Store AI commentary data
            self.ai_data = {}
            for item in data:
                qid = item.get('id')
                if qid not in self.ai_data:
                    self.ai_data[qid] = {
                        'answer_ai': item.get('answer_ai'),
                        'discussion_ai': item.get('discussion_ai'),
                        'justification_ai': item.get('justification_ai'),
                        'source_ai': item.get('source_ai')
                    }
            logger.info(f"Fetched {len(self.questions_df)} questions from API")
        except Exception as e:
            logger.error(f"Error fetching questions from API: {e}")
            raise

    def get_question_by_id(self, question_id: int) -> Dict:
        """Retrieve a question and its associated answers by ID"""
        if self.questions_df is None:
            raise RuntimeError("Questions have not been loaded")
            
        question = self.questions_df[self.questions_df['question_id'] == question_id].to_dict('records')
        if not question:
            return None
            
        question = question[0]
        
        # Add correct answer
        correct_answer = self.correct_answers_df[
            self.correct_answers_df['question_id'] == question_id
        ]['answer_text'].iloc[0] if not self.correct_answers_df.empty else None
        
        # Add incorrect answers if available
        incorrect_answers = self.incorrect_answers_df[
            self.incorrect_answers_df['question_id'] == question_id
        ]['answer_text'].tolist() if not self.incorrect_answers_df.empty else []
        # Include source from AI data if available
        ai_info = getattr(self, 'ai_data', {}).get(question_id, {})
        source = ai_info.get('source_ai')

        return {
            **question,
            'correct_answer': correct_answer,
            'incorrect_answers': incorrect_answers,
            'source': source
        }

    def get_questions_by_topic(self, topic: str) -> List[Dict]:
        """Retrieve all questions for a specific topic"""
        if self.questions_df is None:
            raise RuntimeError("Questions have not been loaded")
            
        questions = self.questions_df[self.questions_df['topic'] == topic].to_dict('records')
        return [self.get_question_by_id(q['question_id']) for q in questions]

# Create a singleton instance
question_manager = QuestionManager()
