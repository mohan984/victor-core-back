# your_app/urls.py

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExamViewSet,
    SubExamViewSet,
    TestCardViewSet,
    TestSubmissionViewSet,
    RevisionLogViewSet,
    ChallengeTestViewSet,
    WeeklyQuizViewSet, DashboardViewSet,
    PerformanceHubViewSet # Add this import
)

router = DefaultRouter()

# Register all viewsets
router.register(r'exams', ExamViewSet, basename='exam')
router.register(r'sub-exams', SubExamViewSet, basename='subexam')
router.register(r'test-cards', TestCardViewSet, basename='testcard')
router.register(r'submissions', TestSubmissionViewSet, basename='submission')
router.register(r'revision-log', RevisionLogViewSet, basename='revisionlog')
router.register(r'challenges', ChallengeTestViewSet, basename='challenge')
router.register(r'weekly-quizzes', WeeklyQuizViewSet, basename='weeklyquiz')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')
router.register(r'performance-hub', PerformanceHubViewSet, basename='performance-hub')


urlpatterns = [
    path('api/', include(router.urls)),
]

# Available API Endpoints:
# 
# EXAMS & CONTENT:
# GET    /api/exams/                              - List all exams with sub-exams
# GET    /api/exams/{id}/                         - Get specific exam details
# GET    /api/sub-exams/                          - List all sub-exams
# GET    /api/sub-exams/{id}/                     - Get specific sub-exam
# GET    /api/sub-exams/{id}/study_notes/         - Get study notes for sub-exam
# GET    /api/sub-exams/{id}/mind_maps/           - Get mind maps for sub-exam
# GET    /api/sub-exams/{id}/flashcards/          - Get flashcards for sub-exam
#
# TEST CARDS:
# GET    /api/test-cards/                         - List all test cards (filter: ?sub_exam=X&test_type=Y)
# GET    /api/test-cards/{id}/                    - Get test card with questions
# GET    /api/test-cards/{id}/check_unlock_status/ - Check if test is unlocked
# POST   /api/test-cards/{id}/unlock_full_length_test/ - Purchase full-length test
#
# TEST SUBMISSIONS:
# POST   /api/submissions/start_test/             - Start a new test attempt
#        Body: {"test_card_id": "test123"}
# POST   /api/submissions/{id}/submit_test/       - Submit completed test
#        Body: {"answers": [{"question_id": 1, "selected_option": "A", "is_marked": true, "mark_reason": "GUESS"}]}
# GET    /api/submissions/my_results/             - Get all user's results (filter: ?test_card_id=X)
# GET    /api/submissions/{id}/                   - Get specific submission result
# GET    /api/submissions/performance_summary/    - Get overall performance stats
#
# REVISION LOG:
# GET    /api/revision-log/                       - Get user's revision log (filter: ?reason=X&test_card_id=Y)
# GET    /api/revision-log/summary/               - Get revision log summary
#
# CHALLENGES & WEEKLY QUIZ (Admin only):
# POST   /api/challenges/create_from_revision_log/ - Create challenge from user's revision log
#        Body: {"user_id": 1, "sub_exam_id": "sub1", "name": "Challenge 1", "reward_points": 5}
# POST   /api/weekly-quizzes/create_weekly_quiz/  - Create weekly quiz from all users
#        Body: {"sub_exam_id": "sub1", "name": "Week 1 Quiz", "reward_points": 10}