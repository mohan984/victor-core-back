# your_app/utils.py

from django.db.models import Count, Avg, Q, Sum, Case, When, F, Window

from .models import TestSubmission, RevisionLog, Question, TestCard,Answer
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, Rank, ExtractHour
from datetime import timedelta
from django.utils import timezone



def get_user_performance_analytics(user):
    """
    Generate detailed performance analytics for a user.
    """
    submissions = TestSubmission.objects.filter(
        user=user,
        status=TestSubmission.Status.COMPLETED
    )
    
    if not submissions.exists():
        return {
            'total_tests': 0,
            'message': 'No completed tests yet'
        }
    
    analytics = {
        'total_tests_completed': submissions.count(),
        'total_reward_points': user.profile.reward_points,
        'overall_average': submissions.aggregate(Avg('percentage'))['percentage__avg'],
        'highest_score': submissions.order_by('-percentage').first().percentage,
        'lowest_score': submissions.order_by('percentage').first().percentage,
        'subject_wise_performance': [],
        'recent_tests': []
    }
    
    # Subject-wise breakdown
    subject_tests = submissions.filter(
        test_card__test_type=TestCard.TestType.SUBJECT_WISE
    ).values(
        'test_card__sub_exam__name'
    ).annotate(
        count=Count('id'),
        avg_percentage=Avg('percentage')
    )
    
    analytics['subject_wise_performance'] = list(subject_tests)
    
    # Recent 5 tests
    recent = submissions.order_by('-finished_at')[:3].values(
        'test_card__name',
        'percentage',
        'attempt_number',
        'finished_at'
        'test_card_id', # ADD THIS
    )
    analytics['recent_tests'] = list(recent)
    
    return analytics


def get_weak_areas(user):
    """
    Identify weak areas based on revision log.
    """
    weak_areas = RevisionLog.objects.filter(
        user=user
    ).values(
        'question__topic',
        'question__section'
    ).annotate(
        error_count=Count('id')
    ).order_by('-error_count')[:10]
    
    return list(weak_areas)


def get_next_unlockable_tests(user, sub_exam):
    """
    Get the tests that could be unlocked next for a user in a sub-exam.
    """
    # Get all subject-wise tests for this sub-exam
    all_tests = TestCard.objects.filter(
        sub_exam=sub_exam,
        test_type=TestCard.TestType.SUBJECT_WISE
    ).order_by('order')
    
    # Get unlocked tests
    unlocked_ids = user.unlocked_tests.filter(
        test_card__sub_exam=sub_exam
    ).values_list('test_card_id', flat=True)
    
    # Find the first locked test
    for test in all_tests:
        if test.id not in unlocked_ids:
            return test
    
    return None  # All tests unlocked


def calculate_streak(user):
    """
    Calculate the user's current test-taking streak (consecutive days).
    """
    
    submissions = TestSubmission.objects.filter(
        user=user,
        status=TestSubmission.Status.COMPLETED
    ).order_by('-finished_at')
    
    if not submissions.exists():
        return 0
    
    streak = 1
    last_date = submissions.first().finished_at.date()
    
    for submission in submissions[1:]:
        current_date = submission.finished_at.date()
        diff = (last_date - current_date).days
        
        if diff == 1:
            streak += 1
            last_date = current_date
        elif diff > 1:
            break
    
    return streak


def prepare_revision_quiz_questions(user, limit=20):
    """
    Prepare a set of questions from user's revision log for a quiz.
    Prioritizes questions the user got wrong most frequently.
    """
    # Get questions from revision log with frequency
    question_ids = RevisionLog.objects.filter(
        user=user
    ).values('question_id').annotate(
        frequency=Count('id')
    ).order_by('-frequency')[:limit].values_list('question_id', flat=True)
    
    questions = Question.objects.filter(id__in=question_ids)
    return questions


def prepare_global_quiz_questions(limit=25):
    """
    Prepare questions for a weekly quiz based on all users' revision logs.
    Selects questions that many users struggled with.
    """
    # Get questions that appear in many users' revision logs
    common_questions = RevisionLog.objects.values('question_id').annotate(
        user_count=Count('user', distinct=True),
        total_occurrences=Count('id')
    ).order_by('-user_count', '-total_occurrences')[:limit]
    
    question_ids = [q['question_id'] for q in common_questions]
    questions = Question.objects.filter(id__in=question_ids)
    
    return questions


def get_advanced_performance_data(user, time_filter='month'):
    """
    Gathers all analytics data needed for the advanced performance hub dashboard.
    """
    now = timezone.now()
    if time_filter == 'week':
        start_date = now - timedelta(days=7)
    elif time_filter == 'month':
        start_date = now - timedelta(days=30)
    else: # all-time
        start_date = None

    submissions = TestSubmission.objects.filter(user=user, status=TestSubmission.Status.COMPLETED)
    if start_date:
        submissions = submissions.filter(finished_at__gte=start_date)

    if not submissions.exists():
        return {'message': 'No data for the selected period.'}

    # === Calculate Key Metrics ===
    aggregates = submissions.aggregate(avg_score=Avg('percentage'), total_tests=Count('id'))
    total_answers = Answer.objects.filter(submission__in=submissions)
    correct_answers = total_answers.filter(is_correct=True).count()
    attempted_answers = total_answers.filter(selected_option__isnull=False).count()

    # === Performance Trend (Grouped by Week) ===
    performance_trend = submissions.annotate(
        week=TruncWeek('finished_at')
    ).values('week').annotate(
        score=Avg('percentage'),
        tests=Count('id')
    ).order_by('week')

    # === Subject-wise Performance ===
    subject_performance = submissions.values('test_card__sub_exam__name').annotate(
        score=Avg('percentage'),
        tests=Count('id'),
        accuracy=Avg(Case(When(answers__is_correct=True, then=1.0), default=0.0)) * 100
    ).order_by('-score')

    # === Topic/Question Type Analysis ===
    topic_analysis = Answer.objects.filter(submission__in=submissions).values('question__topic').annotate(
        correct=Count(Case(When(is_correct=True, then=1))),
        wrong=Count(Case(When(is_correct=False, selected_option__isnull=False, then=1))),
        skipped=Count(Case(When(selected_option__isnull=True, then=1))),
        total=Count('id')
    ).filter(question__topic__isnull=False).exclude(question__topic__exact='')

    # === Peak Performance Hours ===
    learning_pattern = submissions.annotate(
    hour=ExtractHour('finished_at') # Extracts the hour as an integer
).values('hour').annotate(
    focus=Avg('percentage'),
    tests=Count('id')
).order_by('hour')

    # === Assemble the data structure ===
    data = {
        'quick_stats': {
            'total_tests_completed': aggregates['total_tests'],
            'avg_score': aggregates['avg_score'] or 0,
            'study_streak': calculate_streak(user),
            'accuracy': (correct_answers / attempted_answers) * 100 if attempted_answers > 0 else 0,
        },
        'performance_trend': list(performance_trend),
        'subject_performance': list(subject_performance),
        'question_analysis': list(topic_analysis),
        'learning_pattern': list(learning_pattern),
        'recent_activity': list(submissions.order_by('-finished_at')[:4].values(
            'id', 'test_card__name', 'percentage', 'finished_at'
        )),
        # Leaderboard and Achievements would be added here
        'leaderboard': [], # Placeholder for now
    }
    return data

