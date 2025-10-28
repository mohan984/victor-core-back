# your_app/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from accounts.models import UserProfile
# -----------------------------------------------------------------------------
# CORE USER AND CONTENT MODELS
# -----------------------------------------------------------------------------



class Exam(models.Model):
    """Represents a major exam category, e.g., 'General Knowledge'."""
    id = models.CharField(max_length=50, primary_key=True)
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


class SubExam(models.Model):
    """Represents a sub-topic within an Exam, e.g., 'History of India'."""
    id = models.CharField(max_length=50, primary_key=True)
    exam = models.ForeignKey(Exam, related_name='sub_exams', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.exam.name} - {self.name}"


# --- New Content Models ---

class StudyNote(models.Model):
    """Stores educational notes related to a SubExam."""
    sub_exam = models.ForeignKey(SubExam, related_name='study_notes', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class MindMap(models.Model):
    """Stores mind maps (e.g., as images) for a SubExam."""
    sub_exam = models.ForeignKey(SubExam, related_name='mind_maps', on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    image = models.ImageField(upload_to='mind_maps/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Flashcard(models.Model):
    """Stores double-sided flashcards for a SubExam."""
    sub_exam = models.ForeignKey(SubExam, related_name='flashcards', on_delete=models.CASCADE)
    front_content = models.TextField()
    back_content = models.TextField()

    def __str__(self):
        return f"Flashcard for {self.sub_exam.name} - {self.front_content[:30]}..."


# -----------------------------------------------------------------------------
# TEST AND QUESTION MODELS
# -----------------------------------------------------------------------------

class TestCard(models.Model):
    """
    Represents an individual test or quiz. Can be a subject test, full-length test,
    challenge, or weekly quiz.
    """
    class TestType(models.TextChoices):
        SUBJECT_WISE = 'SUBJECT', 'Subject Wise'
        FULL_LENGTH = 'FULL', 'Full Length'
        CHALLENGE = 'CHALLENGE', 'Challenge Test'
        WEEKLY_QUIZ = 'QUIZ', 'Weekly Quiz'

    id = models.CharField(max_length=50, primary_key=True)
    sub_exam = models.ForeignKey(SubExam, related_name='test_cards', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    test_type = models.CharField(max_length=10, choices=TestType.choices, default=TestType.SUBJECT_WISE)
    order = models.PositiveIntegerField(default=1, help_text="Sequence for unlocking subject-wise tests.")
    duration_minutes = models.PositiveIntegerField(default=60)
    price_points = models.PositiveIntegerField(default=0, help_text="Reward points required to unlock this test.")
    reward_points = models.PositiveIntegerField(default=0, help_text="Reward points earned for completing this test (for challenges and quizzes).")
    is_active = models.BooleanField(default=True, help_text="Whether the test is available for users.")

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"[{self.get_test_type_display()}] {self.sub_exam.name} → {self.name}"


class Question(models.Model):
    """Represents a single question within a TestCard."""
    class Difficulty(models.TextChoices):
        EASY = 'Easy', 'Easy'
        MEDIUM = 'Medium', 'Medium'
        HARD = 'Hard', 'Hard'

    class Option(models.TextChoices):
        A = 'A', 'Option A'
        B = 'B', 'Option B'
        C = 'C', 'Option C'
        D = 'D', 'Option D'

    test_card = models.ForeignKey(TestCard, related_name='questions', on_delete=models.CASCADE)
    question_text = models.TextField()
    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)
    correct_option = models.CharField(max_length=1, choices=Option.choices)
    
    # --- Additional Metadata ---
    section = models.CharField(max_length=100, default="General")
    topic = models.CharField(max_length=100, blank=True)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices, default=Difficulty.MEDIUM)
    positive_marks = models.FloatField(default=1.0)
    negative_marks = models.FloatField(default=0.25) # Standard negative marking

    def __str__(self):
        return f"{self.test_card.name}: {self.question_text[:50]}"


# -----------------------------------------------------------------------------
# USER PROGRESS AND SUBMISSION MODELS
# -----------------------------------------------------------------------------

class UnlockedTestCard(models.Model):
    """Tracks which tests a user has unlocked."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="unlocked_tests")
    test_card = models.ForeignKey(TestCard, on_delete=models.CASCADE, related_name="unlocked_by")
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'test_card') # User can unlock a test only once

    def __str__(self):
        return f"{self.user.username} unlocked {self.test_card.name}"


class TestSubmission(models.Model):
    """Stores an overall record of a single attempt at a test by a user."""
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In Progress'
        COMPLETED = 'completed', 'Completed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    test_card = models.ForeignKey(TestCard, on_delete=models.CASCADE, related_name="submissions")
    attempt_number = models.PositiveIntegerField(default=1)
    score = models.FloatField(default=0)
    percentage = models.FloatField(default=0, help_text="Score in percentage (0-100).")
    reward_points_earned = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} → {self.test_card.name} (Attempt {self.attempt_number})"


class Answer(models.Model):
    """Stores the specific answer a user gave for a question in a submission."""
    class MarkReason(models.TextChoices):
        GUESS = 'GUESS', 'Guess'
        TIME_PRESSURE = 'TIME', 'Time Pressure'
        CONCEPT_ERROR = 'CONCEPT', 'Concept Error'

    submission = models.ForeignKey(TestSubmission, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    selected_option = models.CharField(max_length=1, choices=Question.Option.choices, null=True, blank=True)
    is_correct = models.BooleanField(default=False)
    
    # --- Revision Log Fields ---
    is_marked = models.BooleanField(default=False, help_text="Did the user explicitly mark this for review?")
    mark_reason = models.CharField(
        max_length=10, choices=MarkReason.choices, blank=True, null=True,
        help_text="The user's reason for marking the question."
    )

    def save(self, *args, **kwargs):
        # Auto-check correctness before saving if an option was selected
        if self.selected_option:
            self.is_correct = (self.selected_option == self.question.correct_option)
        else:
            self.is_correct = False
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Ans for Q{self.question.id} in Sub-{self.submission.id}"


class RevisionLog(models.Model):
    """A personalized collection of questions for each user to revise."""
    class Reason(models.TextChoices):
        INCORRECT = 'INCORRECT', 'Incorrect Answer'
        MARKED_GUESS = 'MARKED_GUESS', 'Marked: Guess'
        MARKED_TIME = 'MARKED_TIME', 'Marked: Time Pressure'
        MARKED_CONCEPT = 'MARKED_CONCEPT', 'Marked: Concept Error'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="revision_log")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="revision_entries")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    
    # Store context of where this question came from
    source_test_card = models.ForeignKey(TestCard, on_delete=models.CASCADE, related_name="revision_sources")
    source_submission_attempt = models.PositiveIntegerField()

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Prevent adding the same question for the same reason from the same attempt
        unique_together = ('user', 'question', 'source_test_card', 'source_submission_attempt')

    def __str__(self):
        return f"{self.user.username}'s revision for Q{self.question.id} ({self.get_reason_display()})"