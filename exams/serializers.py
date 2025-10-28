from rest_framework import serializers
from django.contrib.auth.models import User
from accounts.models import UserProfile 
from collections import defaultdict
from .models import (
    Exam,
    SubExam,
    StudyNote,
    MindMap,
    Flashcard,
    TestCard,
    Question,
    UnlockedTestCard,
    TestSubmission,
    Answer,
    RevisionLog
)

# -----------------------------------------------------------------------------
# USER AND PROFILE SERIALIZERS
# -----------------------------------------------------------------------------
# You need a simple UserSerializer to represent the user in other serializers
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']

# -----------------------------------------------------------------------------
# CORE CONTENT SERIALIZERS
# -----------------------------------------------------------------------------

class TestCardListSerializer(serializers.ModelSerializer):
    """A lightweight serializer for listing TestCards."""
    num_questions = serializers.SerializerMethodField()

    class Meta:
        model = TestCard
        fields = ['id', 'name', 'test_type', 'order', 'price_points','duration_minutes','num_questions']

    def get_num_questions(self, obj):
     return obj.questions.count()
    
   

class SubExamWithFullLengthTestsSerializer(serializers.ModelSerializer):
    """
    A specific serializer to show a SubExam with ONLY its full-length tests.
    """
    # We rename this field to be explicit
    full_length_tests = TestCardListSerializer(
        source='test_cards', many=True, read_only=True
    )

    class Meta:
        model = SubExam
        fields = ['id', 'name', 'full_length_tests']
  


class SubExamSerializer(serializers.ModelSerializer):
    
    
    class Meta:
        model = SubExam
        fields = ['id', 'name']


class ExamSerializer(serializers.ModelSerializer):
    sub_exams = SubExamSerializer(many=True, read_only=True)
    class Meta:
        model = Exam
        fields = ['id', 'name','sub_exams']


# -----------------------------------------------------------------------------
# LEARNING MATERIAL SERIALIZERS
# -----------------------------------------------------------------------------

class StudyNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudyNote
        fields = '__all__'


class MindMapSerializer(serializers.ModelSerializer):
    class Meta:
        model = MindMap
        fields = '__all__'


class FlashcardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Flashcard
        fields = '__all__'


# -----------------------------------------------------------------------------
# TEST TAKING AND RESULTS SERIALIZERS
# -----------------------------------------------------------------------------

class QuestionSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying a question during a test.
    **Excludes the correct_option** to prevent cheating.
    """
    class Meta:
        model = Question
        exclude = ['correct_option']
       

class TestCardDetailSerializer(serializers.ModelSerializer):
    """Serializer for starting a test, providing questions."""
    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = TestCard
        fields = [
            'id', 'name', 'sub_exam', 'test_type', 
            'duration_minutes', 'questions'
        ]


class AnswerSubmitSerializer(serializers.ModelSerializer):
    """Serializer used by the user to submit an answer."""
    question_id = serializers.PrimaryKeyRelatedField(
        queryset=Question.objects.all(), source='question', write_only=True
    )
    
    class Meta:
        model = Answer
        fields = ['question_id', 'selected_option', 'is_marked', 'mark_reason']


class TestSubmissionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating a new test submission."""
    answers = AnswerSubmitSerializer(many=True, write_only=True)

    class Meta:
        model = TestSubmission
        fields = ['test_card', 'answers']


# --- Serializers for Displaying Results ---

class QuestionResultSerializer(serializers.ModelSerializer):
    """
    Serializer for showing a question in the results view.
    **Includes the correct_option**.
    """
    class Meta:
        model = Question
        fields = '__all__'


class AnswerResultSerializer(serializers.ModelSerializer):
    """Serializer for displaying a submitted answer with its question details."""
    question = QuestionResultSerializer(read_only=True)
    
    class Meta:
        model = Answer
        fields = '__all__'


class TestSubmissionResultSerializer(serializers.ModelSerializer):
    performance_analysis = serializers.SerializerMethodField()
    """
    The main serializer for showing a user their complete test result,
    including all questions, their answers, and the correct answers.
    """
    answers = AnswerResultSerializer(many=True, read_only=True)
    test_card = TestCardListSerializer(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = TestSubmission
        fields = [
            'id', 'user', 'test_card', 'attempt_number', 'score',
            'percentage', 'reward_points_earned', 'status', 'finished_at', 'answers','performance_analysis'
        ]
    def get_performance_analysis(self, obj):
        """
        Calculates detailed performance stats for the submission.
        """
        answers = obj.answers.select_related('question').all()
        
        if not answers:
            return None

        total_questions = obj.test_card.questions.count()
        attempted_count = 0
        correct_count = 0

        by_section = defaultdict(lambda: {'correct': 0, 'total': 0})
        by_difficulty = defaultdict(lambda: {'correct': 0, 'total': 0})

        for answer in answers:
            question = answer.question
            section = question.section
            difficulty = question.difficulty

            # Aggregate stats for sections and difficulty
            by_section[section]['total'] += 1
            by_difficulty[difficulty]['total'] += 1
            
            if answer.selected_option:
                attempted_count += 1
            
            if answer.is_correct:
                correct_count += 1
                by_section[section]['correct'] += 1
                by_difficulty[difficulty]['correct'] += 1
        
        # Calculate percentages for each category
        for section_stats in by_section.values():
            section_stats['percentage'] = (section_stats['correct'] / section_stats['total']) * 100 if section_stats['total'] > 0 else 0
        
        for diff_stats in by_difficulty.values():
            diff_stats['percentage'] = (diff_stats['correct'] / diff_stats['total']) * 100 if diff_stats['total'] > 0 else 0

        # Assemble the final analysis object
        analysis = {
            'accuracy': (correct_count / attempted_count) * 100 if attempted_count > 0 else 0,
            'by_section': dict(by_section),
            'by_difficulty': dict(by_difficulty),
            # You can add more logic here for skill proficiency or trends if needed
        }
        
        return analysis
# -----------------------------------------------------------------------------
# USER PROGRESS AND REVISION SERIALIZERS
# -----------------------------------------------------------------------------

class UnlockedTestCardSerializer(serializers.ModelSerializer):
    """Serializer to show which tests a user has unlocked."""
    test_card = TestCardListSerializer(read_only=True)

    class Meta:
        model = UnlockedTestCard
        fields = ['test_card', 'unlocked_at']


class RevisionLogSerializer(serializers.ModelSerializer):
    """Serializer for a user's revision log."""
    question = QuestionSerializer(read_only=True)
    user = UserSerializer(read_only=True)

    class Meta:
        model = RevisionLog
        fields = '__all__'

# your_app/serializers.py
# ... (add this at the end of the file)

class DashboardDataSerializer(serializers.Serializer):
    """
    Serializer for the aggregated data needed for the main performance dashboard.
    """
    total_tests_completed = serializers.IntegerField()
    overall_average = serializers.FloatField()
    highest_score = serializers.FloatField()
    lowest_score = serializers.FloatField()
    subject_wise_performance = serializers.ListField(child=serializers.DictField())
    recent_tests = serializers.ListField(child=serializers.DictField())
    achievements = serializers.ListField(child=serializers.CharField())
    # Add any other fields from your utils function as needed

class PerformanceHubSerializer(serializers.Serializer):
    """Serializer for the advanced performance hub dashboard."""
    quick_stats = serializers.DictField()
    performance_trend = serializers.ListField()
    subject_performance = serializers.ListField()
    question_analysis = serializers.ListField()
    learning_pattern = serializers.ListField()
    recent_activity = serializers.ListField()
    leaderboard = serializers.ListField()
