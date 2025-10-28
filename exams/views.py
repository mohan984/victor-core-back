# your_app/views.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q, Avg , Prefetch
from django.db import transaction
from .serializers import SubExamWithFullLengthTestsSerializer, DashboardDataSerializer,PerformanceHubSerializer
from .utils import get_user_performance_analytics ,get_advanced_performance_data
from .permissions import IsSubscribed # <-- IMPORT YOUR NEW PERMISSION



from .models import (
    Exam, SubExam, StudyNote, MindMap, Flashcard,
    TestCard, Question, UnlockedTestCard, TestSubmission,
    Answer, RevisionLog, UserProfile
)
from .serializers import (
    ExamSerializer, SubExamSerializer,
    StudyNoteSerializer, MindMapSerializer, FlashcardSerializer,
    TestCardDetailSerializer, TestCardListSerializer,
    TestSubmissionCreateSerializer, TestSubmissionResultSerializer,
    UnlockedTestCardSerializer, RevisionLogSerializer, AnswerSubmitSerializer
)


# -----------------------------------------------------------------------------
# CONTENT VIEWSETS (Exams, SubExams, Learning Materials)
# -----------------------------------------------------------------------------

class ExamViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for listing and retrieving exams with their sub-exams."""
    queryset = Exam.objects.all().prefetch_related('sub_exams__test_cards')
    serializer_class = ExamSerializer
    

    def get_queryset(self):
        """
        Optionally filters exams to only include those that have 
        subject-wise test cards.
        """
        # Start with the base queryset
        queryset = super().get_queryset() 
        
        # Check if the query parameter '?has_subject_tests=true' is in the URL
        has_subject_tests = self.request.query_params.get('has_subject_tests', 'false').lower() == 'true'

        if has_subject_tests:
            # If the parameter is present, apply the filter.
            # This looks through the relationships: Exam -> SubExam -> TestCard
            # and checks the test_type field.
            # .distinct() ensures each Exam is only listed once.
            queryset = queryset.filter(
                sub_exams__test_cards__test_type='SUBJECT'
            ).distinct()
            
        return queryset




class SubExamViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for retrieving sub-exam details."""
    queryset = SubExam.objects.all().prefetch_related('test_cards')
    serializer_class = SubExamSerializer
    permission_classes = [IsAuthenticated]
     
    def get_queryset(self):
        """
        Optionally filters the sub-exams by a given 'exam' query parameter.
        """
        queryset = super().get_queryset()
        exam_id = self.request.query_params.get('exam', None)
        if exam_id is not None:
            queryset = queryset.filter(exam_id=exam_id)
        return queryset

    @action(detail=False, methods=['get'])
    def with_full_length_tests(self, request):
        """
        Returns a list of SubExams that contain at least one full-length test.
        Each SubExam object will only include its pre-filtered full-length tests.
        """
        # This queryset is more efficient.
        # It finds SubExams with full-length tests and then pre-fetches ONLY those tests.
        queryset = SubExam.objects.annotate(
            full_test_count=Count('test_cards', filter=Q(test_cards__test_type=TestCard.TestType.FULL_LENGTH))
        ).filter(full_test_count__gt=0).prefetch_related(
            Prefetch(
                'test_cards',
                queryset=TestCard.objects.filter(test_type=TestCard.TestType.FULL_LENGTH),
            )
        )
        
        # Now we can use the serializer directly on the clean queryset
        serializer = SubExamWithFullLengthTestsSerializer(queryset, many=True)
        return Response(serializer.data)


    @action(detail=True, methods=['get'])
    def study_notes(self, request, pk=None):
        """Get all study notes for a sub-exam."""
        sub_exam = self.get_object()
        notes = sub_exam.study_notes.all()
        serializer = StudyNoteSerializer(notes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def mind_maps(self, request, pk=None):
        """Get all mind maps for a sub-exam."""
        sub_exam = self.get_object()
        mind_maps = sub_exam.mind_maps.all()
        serializer = MindMapSerializer(mind_maps, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def flashcards(self, request, pk=None):
        """Get all flashcards for a sub-exam."""
        sub_exam = self.get_object()
        flashcards = sub_exam.flashcards.all()
        serializer = FlashcardSerializer(flashcards, many=True)
        return Response(serializer.data)


# -----------------------------------------------------------------------------
# TEST CARD VIEWSET
# -----------------------------------------------------------------------------

class TestCardViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for managing test cards."""
    queryset = TestCard.objects.filter(is_active=True)
    permission_classes = [IsAuthenticated]
    

    

    @action(detail=True, methods=['get'])
    def check_unlock_status(self, request, pk=None):
        """Check if a test card is unlocked for the current user."""
        test_card = self.get_object()
        user = request.user
        
        # Check if it's a subject-wise test (unlocked by progression)
        if test_card.test_type == TestCard.TestType.SUBJECT_WISE:
            is_unlocked = self._is_subject_test_unlocked(user, test_card)
            return Response({
                'test_card_id': test_card.id,
                'is_unlocked': is_unlocked,
                'unlock_type': 'progression',
                'price_points': 0
            })
        
        # Check if it's a full-length test (unlocked by purchase)
        elif test_card.test_type == TestCard.TestType.FULL_LENGTH:
            unlocked = UnlockedTestCard.objects.filter(
                user=user, test_card=test_card
            ).exists()
            
            user_profile = UserProfile.objects.get(user=user)
            can_afford = user_profile.reward_points >= test_card.price_points
            
            return Response({
                'test_card_id': test_card.id,
                'is_unlocked': unlocked,
                'unlock_type': 'purchase',
                'price_points': test_card.price_points,
                'user_points': user_profile.reward_points,
                'can_afford': can_afford
            })
        
        # Challenge and Weekly Quiz are always accessible
        else:
            return Response({
                'test_card_id': test_card.id,
                'is_unlocked': True,
                'unlock_type': 'special',
                'price_points': 0
            })

    def _is_subject_test_unlocked(self, user, test_card):
        """
        Check if a subject-wise test is unlocked based on progression logic.
        First test is always unlocked. Others unlock based on previous performance.
        """
        # Get all test cards for this sub_exam ordered by sequence
        all_tests = TestCard.objects.filter(
            sub_exam=test_card.sub_exam,
            test_type=TestCard.TestType.SUBJECT_WISE
        ).order_by('order')
        
        # First test is always unlocked
        if test_card == all_tests.first():
            return True
        
        # Check if user has unlocked this specific test
        unlocked = UnlockedTestCard.objects.filter(
            user=user, test_card=test_card
        ).exists()
        
        return unlocked

    @action(detail=True, methods=['post'])
    def unlock_full_length_test(self, request, pk=None):
        """
        Unlock a full-length test by deducting reward points.
        User must pay 15 points each time they want to attempt.
        """
        test_card = self.get_object()
        user = request.user
        
        if test_card.test_type != TestCard.TestType.FULL_LENGTH:
            return Response(
                {'error': 'Only full-length tests can be purchased.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user_profile = UserProfile.objects.get(user=user)
        
        # Check if user has enough points
        if user_profile.reward_points < test_card.price_points:
            return Response(
                {
                    'error': 'Insufficient reward points.',
                    'required': test_card.price_points,
                    'available': user_profile.reward_points
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Deduct points and create unlock record
        with transaction.atomic():
            user_profile.reward_points -= test_card.price_points
            user_profile.save()
            
            unlock_record = UnlockedTestCard.objects.create(
                user=user,
                test_card=test_card
            )
        
        return Response({
            'message': 'Test unlocked successfully',
            'remaining_points': user_profile.reward_points,
            'unlocked_at': unlock_record.unlocked_at
        })
    
    
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestCardDetailSerializer
        return TestCardListSerializer

    def get_queryset(self):
        """Filter test cards based on sub_exam if provided."""
        queryset = super().get_queryset()
        sub_exam_id = self.request.query_params.get('sub_exam', None)
        test_type = self.request.query_params.get('test_type', None)
        
        if sub_exam_id:
            queryset = queryset.filter(sub_exam_id=sub_exam_id)
        if test_type:
            queryset = queryset.filter(test_type=test_type)
        
        return queryset.prefetch_related('questions')
   


# -----------------------------------------------------------------------------
# TEST SUBMISSION VIEWSET
# -----------------------------------------------------------------------------

class TestSubmissionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing test submissions."""
    permission_classes = [IsAuthenticated] 

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        # If the action is 'start_test', we require the user
        # to be BOTH Authenticated AND Subscribed.
        if self.action == 'start_test':
            return [IsAuthenticated(), IsSubscribed()]
        
        # For all other actions, use the default permissions (just IsAuthenticated)
        return super().get_permissions()

    # --- END OF KEY CHANGE ---
    
    @action(detail=False, methods=['post'])
    def start_test(self, request):
        """
        Start a new test attempt for a user.
        Validates unlock status and creates a submission record.
        """
        test_card_id = request.data.get('test_card_id')
        test_card = get_object_or_404(TestCard, id=test_card_id)
        user = request.user

        
        # Validate if test is unlocked
        if test_card.test_type == TestCard.TestType.SUBJECT_WISE:
            if not self._is_subject_test_unlocked_helper(user, test_card):
                return Response(
                    {'error': 'This test is locked. Complete previous tests to unlock.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        elif test_card.test_type == TestCard.TestType.FULL_LENGTH:
            # Check if user has purchased/unlocked this test
            unlocked = UnlockedTestCard.objects.filter(
                user=user, test_card=test_card
            ).exists()
            
            if not unlocked:
                return Response(
                    {'error': 'You must purchase this test first.'},
                    status=status.HTTP_403_FORBIDDEN
                )
            # For full-length tests, delete the unlock record after starting
            # (user must buy again for next attempt)
            UnlockedTestCard.objects.filter(user=user, test_card=test_card).delete()
          # --- ADD THIS BLOCK to handle the one-time attempt for weekly quizzes ---
        elif test_card.test_type == TestCard.TestType.WEEKLY_QUIZ:
            # Check if any submission (in-progress or completed) already exists
             if TestSubmission.objects.filter(user=user, test_card=test_card).exists():
                return Response(
                    {'error': 'You have already attempted this weekly quiz. Only one attempt is allowed.'},
                    status=status.HTTP_403_FORBIDDEN
                )  
        
        # Get the next attempt number
        attempt_number = TestSubmission.objects.filter(
            user=user, test_card=test_card
        ).count() + 1
        
        # Create submission
        submission = TestSubmission.objects.create(
            user=user,
            test_card=test_card,
            attempt_number=attempt_number,
            status=TestSubmission.Status.IN_PROGRESS
        ) 

        return Response({
            'submission_id': submission.id,
            'test_card': TestCardDetailSerializer(test_card, context={'request': request}).data,
            'started_at': submission.started_at
        })
    
    def get_queryset(self):
        return TestSubmission.objects.filter(user=self.request.user).select_related(
            'test_card', 'test_card__sub_exam'
        ).prefetch_related('answers__question')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return TestSubmissionCreateSerializer
        return TestSubmissionResultSerializer


    @action(detail=True, methods=['post'])
    def submit_test(self, request, pk=None):
        """
        Submit a completed test with all answers.
        Calculate score, award points, unlock next tests, and populate revision log.
        """
        submission = self.get_object()
        user = request.user
        
        if submission.status == TestSubmission.Status.COMPLETED:
            return Response(
                {'error': 'This test has already been submitted.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        answers_data = request.data.get('answers', [])
        marked_questions_for_review = []
        
        with transaction.atomic():
            new_answers = []
              # Process each answer
            for answer_data in answers_data:
                question = get_object_or_404(Question, id=answer_data['question_id'])
                
                # Ensure question belongs to this test
                if question.test_card != submission.test_card:
                    continue
                
                answer = Answer.objects.create(
                    submission=submission,
                    question=question,
                    selected_option=answer_data.get('selected_option'),
                    is_marked=answer_data.get('is_marked', False), 
                )
                new_answers.append(answer) # <--- ADD THE NEW ANSWER TO THE LIST
                
                # Automatically log incorrect answers now.
                if not answer.is_correct and answer.selected_option:
                    self._add_to_revision_log(user, answer, submission, is_marked_flow=False)
            
                # If the user marked it, save it for the next step.
                if answer.is_marked:
                   marked_questions_for_review.append({
                       'question_id': answer.question.id,
                        'question_text': answer.question.question_text
                    })


            # Calculate score
            total_score = self._calculate_score(new_answers)
            total_questions = submission.test_card.questions.count()
            percentage = (total_score / (total_questions * submission.test_card.questions.first().positive_marks)) * 100 if total_questions > 0 else 0
            
            # Award reward points based on performance (for subject-wise tests)
            reward_points = 0
            if submission.test_card.test_type == TestCard.TestType.SUBJECT_WISE:
                reward_points = self._calculate_reward_points(percentage)
            elif submission.test_card.test_type in [TestCard.TestType.CHALLENGE, TestCard.TestType.WEEKLY_QUIZ]:
                reward_points = submission.test_card.reward_points
            
            # Update submission
            submission.score = total_score
            submission.percentage = percentage
            submission.reward_points_earned = reward_points
            submission.status = TestSubmission.Status.COMPLETED
            submission.finished_at = timezone.now()
            submission.save()
            
            # Award points to user
            user_profile = UserProfile.objects.get(user=user)
            user_profile.reward_points += reward_points
            user_profile.save()
            
            # Unlock next tests if subject-wise test
            if submission.test_card.test_type == TestCard.TestType.SUBJECT_WISE:
               self._unlock_next_tests(user, submission)
        
        # Return results
        serializer = self.get_serializer(submission)
        response_data = serializer.data
        response_data['total_questions'] = submission.test_card.questions.count()

        if marked_questions_for_review:
        # If questions were marked, tell the frontend it needs to ask for reasons.
            response_data['requires_mark_review'] = True
            response_data['marked_questions'] = marked_questions_for_review
        else:
        # Otherwise, the flow can proceed directly to the results page.
            response_data['requires_mark_review'] = False

        return Response(response_data)

    def _is_subject_test_unlocked_helper(self, user, test_card):
        """Helper to check unlock status."""
        all_tests = TestCard.objects.filter(
            sub_exam=test_card.sub_exam,
            test_type=TestCard.TestType.SUBJECT_WISE
        ).order_by('order')
        
        if test_card == all_tests.first():
            return True
        
        return UnlockedTestCard.objects.filter(user=user, test_card=test_card).exists()

    def _calculate_score(self, answers_list):
        """Calculate total score for a submission."""
        total_score = 0
        for answer in answers_list:
            if answer.is_correct:
                total_score += answer.question.positive_marks
            elif answer.selected_option:  # Attempted but wrong
                total_score -= answer.question.negative_marks
        return max(0, total_score)  # Score can't be negative

    def _calculate_reward_points(self, percentage):
        """Calculate reward points based on percentage score."""
        if percentage >= 90:
            return 10
        elif percentage >= 85:
            return 7
        elif percentage >= 80:
            return 5
        return 0

    def _unlock_next_tests(self, user, submission):
        """
        Unlock subsequent test cards based on performance.
        80-85%: unlock 2 tests
        85-90%: unlock 3 tests
        >90%: unlock 4 tests
        """
        percentage = submission.percentage
        
        if percentage < 80:
            return  # No unlocks
        
        # Determine how many to unlock
        if percentage >= 90:
            unlock_count = 4
        elif percentage >= 85:
            unlock_count = 3
        else:  # 80-85%
            unlock_count = 2
        
        # Get next tests to unlock
        current_test = submission.test_card
        next_tests = TestCard.objects.filter(
            sub_exam=current_test.sub_exam,
            test_type=TestCard.TestType.SUBJECT_WISE,
            order__gt=current_test.order
        ).order_by('order')[:unlock_count]
        
        # Create unlock records
        for test in next_tests:
            UnlockedTestCard.objects.get_or_create(
                user=user,
                test_card=test
            )

    def _add_to_revision_log(self, user, answer, submission, is_marked_flow=False):
        """Add question to revision log if it was marked or answered incorrectly."""
        reasons_to_add = []
        
        # Check if incorrect
        if is_marked_flow:
        # This flow is for when the user submits reasons from the new page
         if answer.is_marked and answer.mark_reason:
            reason_map = {
                Answer.MarkReason.GUESS: RevisionLog.Reason.MARKED_GUESS,
                Answer.MarkReason.TIME_PRESSURE: RevisionLog.Reason.MARKED_TIME,
                Answer.MarkReason.CONCEPT_ERROR: RevisionLog.Reason.MARKED_CONCEPT,
            }
            if answer.mark_reason in reason_map:
                reasons_to_add.append(reason_map[answer.mark_reason])
        else:
        # This is for the initial submit: only log incorrect answers automatically
          if not answer.is_correct and answer.selected_option:
            reasons_to_add.append(RevisionLog.Reason.INCORRECT)
        
        # Add to revision log for each reason
        for reason in reasons_to_add:
            RevisionLog.objects.get_or_create(
                user=user,
                question=answer.question,
                reason=reason,
                source_test_card=submission.test_card,
                source_submission_attempt=submission.attempt_number
            )
                
              # Add this entire new method to your TestSubmissionViewSet
    @action(detail=True, methods=['post'])
    def save_mark_reasons(self, request, pk=None):
        """
          Receives reasons for marked questions and saves them to the revision log.
        """
        submission = self.get_object()
        user = request.user
        reasons_data = request.data.get('reasons', [])

        with transaction.atomic():
            for reason_item in reasons_data:
                question_id = reason_item.get('question_id')
                reason_key = reason_item.get('reason')  # e.g., 'GUESS', 'TIME', 'CONCEPT'

                try:
                # Find the answer record we created in the previous step
                    answer = Answer.objects.get(
                    submission=submission,
                    question_id=question_id
                      )
                
                     # Now, update it with the reason provided by the user
                    answer.mark_reason = reason_key
                    answer.save()
                
                    # Finally, add this marked question to the revision log
                    self._add_to_revision_log(user, answer, submission, is_marked_flow=True)

                except Answer.DoesNotExist:
                     continue
            
        return Response({'status': 'success'}, status=status.HTTP_200_OK)  
                

    @action(detail=False, methods=['get'])
    def my_results(self, request):
        """Get all test results for the current user."""
        test_card_id = request.query_params.get('test_card_id')
        
        queryset = self.get_queryset().filter(
            status=TestSubmission.Status.COMPLETED
        )
        
        if test_card_id:
            queryset = queryset.filter(test_card_id=test_card_id)
        
        queryset = queryset.order_by('-finished_at')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def performance_summary(self, request):
        """Get performance summary across all tests."""
        user = request.user
        submissions = TestSubmission.objects.filter(
            user=user,
            status=TestSubmission.Status.COMPLETED
        ).select_related('test_card')
        
        summary = {
            'total_tests_completed': submissions.count(),
            'total_reward_points': UserProfile.objects.get(user=user).reward_points,
            'average_percentage': submissions.aggregate(
                avg_percentage=models.Avg('percentage')
            )['avg_percentage'] or 0,
            'tests_by_type': {}
        }
        
        # Group by test type
        for test_type in TestCard.TestType:
            type_submissions = submissions.filter(test_card__test_type=test_type.value)
            if type_submissions.exists():
                summary['tests_by_type'][test_type.label] = {
                    'count': type_submissions.count(),
                    'avg_percentage': type_submissions.aggregate(
                        avg=models.Avg('percentage')
                    )['avg'] or 0
                }
        
        return Response(summary)


# -----------------------------------------------------------------------------
# REVISION LOG VIEWSET
# -----------------------------------------------------------------------------

class RevisionLogViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for accessing user's revision log."""
    serializer_class = RevisionLogSerializer
    permission_classes = [IsAuthenticated]

    
    def get_queryset(self):
        user = self.request.user
        queryset = RevisionLog.objects.filter(user=user).select_related(
            'question', 'source_test_card'
        ).order_by('-added_at')
        
        # Filter by reason if provided
        reason = self.request.query_params.get('reason')
        if reason:
            queryset = queryset.filter(reason=reason)
        
        # Filter by test card if provided
        test_card_id = self.request.query_params.get('test_card_id')
        if test_card_id:
            queryset = queryset.filter(source_test_card_id=test_card_id)
        
        return queryset

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get summary of revision log."""
        user = request.user
        
        summary = {
            'total_questions': RevisionLog.objects.filter(user=user).values('question').distinct().count(),
            'by_reason': {}
        }
        
        for reason in RevisionLog.Reason:
            count = RevisionLog.objects.filter(user=user, reason=reason.value).count()
            if count > 0:
                summary['by_reason'][reason.label] = count
        
        return Response(summary)


# -----------------------------------------------------------------------------
# ADMIN-CREATED CHALLENGE AND WEEKLY QUIZ
# -----------------------------------------------------------------------------

class ChallengeTestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for admin to create challenge tests from revision logs.
    Only accessible by admin/staff users.
    """
    queryset = TestCard.objects.filter(test_type=TestCard.TestType.CHALLENGE)
    serializer_class = TestCardDetailSerializer

    @action(detail=False, methods=['post'])
    def create_from_revision_log(self, request):
        """
        Admin creates a challenge test from a specific user's revision log.
        """
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can create challenges.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        user_id = request.data.get('user_id')
        sub_exam_id = request.data.get('sub_exam_id')
        challenge_name = request.data.get('name', 'Weekly Challenge')
        reward_points = request.data.get('reward_points', 5)
        
        # Get questions from user's revision log
        revision_questions = RevisionLog.objects.filter(
            user_id=user_id
        ).values_list('question_id', flat=True).distinct()[:20]
        
        if not revision_questions:
            return Response(
                {'error': 'No questions in revision log for this user.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create challenge test card
        with transaction.atomic():
            test_card = TestCard.objects.create(
                id=f"challenge_{user_id}_{timezone.now().timestamp()}",
                sub_exam_id=sub_exam_id,
                name=challenge_name,
                test_type=TestCard.TestType.CHALLENGE,
                duration_minutes=30,
                reward_points_earned=reward_points
            )

            # Duplicate questions for this challenge
            questions = Question.objects.filter(id__in=revision_questions)
            for question in questions:
                Question.objects.create(
                    test_card=test_card,
                    question_text=question.question_text,
                    option_a=question.option_a,
                    option_b=question.option_b,
                    option_c=question.option_c,
                    option_d=question.option_d,
                    correct_option=question.correct_option,
                    section=question.section,
                    topic=question.topic,
                    difficulty=question.difficulty,
                    positive_marks=question.positive_marks,
                    negative_marks=question.negative_marks,
                )

        return Response({
            'message': 'Challenge created successfully',
            'test_card_id': test_card.id,
            'reward_points': reward_points
        })


class WeeklyQuizViewSet(viewsets.ModelViewSet):
    """ViewSet for managing weekly quizzes compiled from all users' revision logs."""
    queryset = TestCard.objects.filter(test_type=TestCard.TestType.WEEKLY_QUIZ)
    serializer_class = TestCardDetailSerializer


    @action(detail=False, methods=['post'])
    def create_weekly_quiz(self, request):
        """
        Admin creates a weekly quiz from all users' revision logs.
        """
        if not request.user.is_staff:
            return Response(
                {'error': 'Only admins can create weekly quizzes.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        sub_exam_id = request.data.get('sub_exam_id')
        quiz_name = request.data.get('name', f'Weekly Quiz - {timezone.now().strftime("%Y-%m-%d")}')
        reward_points = request.data.get('reward_points', 10)
        
        # Get most common questions from all users' revision logs
        common_questions = RevisionLog.objects.values('question_id').annotate(
            user_count=Count('user', distinct=True)
        ).order_by('-user_count')[:25]
        
        question_ids = [q['question_id'] for q in common_questions]
        
        if not question_ids:
            return Response(
                {'error': 'No questions available for quiz.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create weekly quiz
        with transaction.atomic():
            test_card = TestCard.objects.create(
                id=f"weekly_quiz_{timezone.now().timestamp()}",
                sub_exam_id=sub_exam_id,
                name=quiz_name,
                test_type=TestCard.TestType.WEEKLY_QUIZ,
                duration_minutes=45,
                reward_points_earned=reward_points
            )

            # Duplicate questions for this quiz
            questions = Question.objects.filter(id__in=question_ids)
            for question in questions:
                Question.objects.create(
                    test_card=test_card,
                    question_text=question.question_text,
                    option_a=question.option_a,
                    option_b=question.option_b,
                    option_c=question.option_c,
                    option_d=question.option_d,
                    correct_option=question.correct_option,
                    section=question.section,
                    topic=question.topic,
                    difficulty=question.difficulty,
                    positive_marks=question.positive_marks,
                    negative_marks=question.negative_marks,
                )

        return Response({
            'message': 'Weekly quiz created successfully',
            'test_card_id': test_card.id,
            'question_count': len(question_ids),
            'reward_points': reward_points
        })


class DashboardViewSet(viewsets.ViewSet):
    """
    A simple ViewSet for providing aggregated dashboard data.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """
        Return a dictionary of all data needed for the user's dashboard.
        """
        user = request.user
        
        # Get the main analytics from your util function
        analytics_data = get_user_performance_analytics(user)
        
        # Get achievements from your util function
        # The signal will handle awarding points, but we need the list for display

        # Serialize the data
        serializer = DashboardDataSerializer(instance=analytics_data)
        return Response(serializer.data)
    
class PerformanceHubViewSet(viewsets.ViewSet):
    

    def list(self, request):
        user = request.user
        time_filter = request.query_params.get('filter', 'month')
        
        data = get_advanced_performance_data(user, time_filter)
        
        if 'message' in data:
            return Response(data)
            
        serializer = PerformanceHubSerializer(instance=data)
        return Response(serializer.data)
