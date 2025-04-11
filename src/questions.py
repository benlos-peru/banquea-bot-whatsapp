import pandas as pd
from pathlib import Path
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class QuestionManager:
    def __init__(self):
        self.questions_df = None
        self.correct_answers_df = None
        self.incorrect_answers_df = None
        self._load_questions()

    def _load_questions(self):
        """Load all question-related CSV files into memory"""
        try:
            base_path = Path(__file__).parent.parent / 'preguntas'
            
            # Load main questions
            questions_path = base_path / 'preguntas.csv'
            self.questions_df = pd.read_csv(questions_path)
            
            # Load correct answers
            correct_answers_path = base_path / 'respuestas_correctas.csv'
            self.correct_answers_df = pd.read_csv(correct_answers_path)
            
            # Load incorrect answers
            incorrect_answers_path = base_path / 'respuestas_incorrectas.csv'
            self.incorrect_answers_df = pd.read_csv(incorrect_answers_path)
            
            logger.info(f"Successfully loaded {len(self.questions_df)} questions")
            
        except Exception as e:
            logger.error(f"Error loading questions: {str(e)}")
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
        
        return {
            **question,
            'correct_answer': correct_answer,
            'incorrect_answers': incorrect_answers
        }

    def get_questions_by_topic(self, topic: str) -> List[Dict]:
        """Retrieve all questions for a specific topic"""
        if self.questions_df is None:
            raise RuntimeError("Questions have not been loaded")
            
        questions = self.questions_df[self.questions_df['topic'] == topic].to_dict('records')
        return [self.get_question_by_id(q['question_id']) for q in questions]

# Create a singleton instance
question_manager = QuestionManager()
