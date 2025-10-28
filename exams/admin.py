# your_app/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    UserProfile, Exam, SubExam, StudyNote, MindMap, Flashcard,
    TestCard, Question, UnlockedTestCard, TestSubmission,
    Answer, RevisionLog
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'reward_points']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['user']


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'sub_exam_count']
    search_fields = ['name']
    
    def sub_exam_count(self, obj):
        return obj.sub_exams.count()
    sub_exam_count.short_description = 'Sub Exams'


@admin.register(SubExam)
class SubExamAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'exam', 'test_card_count']
    list_filter = ['exam']
    search_fields = ['name', 'exam__name']
    
    def test_card_count(self, obj):
        return obj.test_cards.count()
    test_card_count.short_description = 'Test Cards'


@admin.register(StudyNote)
class StudyNoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'sub_exam', 'created_at']
    list_filter = ['sub_exam', 'created_at']
    search_fields = ['title', 'content']


@admin.register(MindMap)
class MindMapAdmin(admin.ModelAdmin):
    list_display = ['title', 'sub_exam', 'image_preview', 'created_at']
    list_filter = ['sub_exam', 'created_at']
    search_fields = ['title']
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return '-'
    image_preview.short_description = 'Preview'


@admin.register(Flashcard)
class FlashcardAdmin(admin.ModelAdmin):
    list_display = ['id', 'sub_exam', 'front_preview']
    list_filter = ['sub_exam']
    search_fields = ['front_content', 'back_content']
    
    def front_preview(self, obj):
        return obj.front_content[:50] + '...' if len(obj.front_content) > 50 else obj.front_content
    front_preview.short_description = 'Front Content'


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 1
    fields = ['question_text', 'correct_option', 'difficulty', 'positive_marks', 'negative_marks']


@admin.register(TestCard)
class TestCardAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'sub_exam', 'test_type', 'order', 'price_points', 'question_count', 'is_active']
    list_filter = ['test_type', 'is_active', 'sub_exam']
    search_fields = ['name', 'sub_exam__name']
    list_editable = ['is_active', 'order']
    inlines = [QuestionInline]
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['id', 'test_card', 'question_preview', 'correct_option', 'difficulty', 'section']
    list_filter = ['test_card', 'difficulty', 'section']
    search_fields = ['question_text', 'topic']
    
    def question_preview(self, obj):
        return obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
    question_preview.short_description = 'Question'


@admin.register(UnlockedTestCard)
class UnlockedTestCardAdmin(admin.ModelAdmin):
    list_display = ['user', 'test_card', 'unlocked_at']
    list_filter = ['test_card__test_type', 'unlocked_at']
    search_fields = ['user__username', 'test_card__name']
    date_hierarchy = 'unlocked_at'


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    readonly_fields = ['question', 'selected_option', 'is_correct', 'is_marked', 'mark_reason']
    can_delete = False


@admin.register(TestSubmission)
class TestSubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'test_card', 'attempt_number', 'percentage', 'reward_points_earned', 'status', 'finished_at']
    list_filter = ['status', 'test_card__test_type', 'finished_at']
    search_fields = ['user__username', 'test_card__name']
    readonly_fields = ['user', 'test_card', 'attempt_number', 'score', 'percentage', 'reward_points_earned', 'started_at', 'finished_at']
    date_hierarchy = 'finished_at'
    inlines = [AnswerInline]
    
    def has_add_permission(self, request):
        return False


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission_user', 'question_preview', 'selected_option', 'is_correct', 'is_marked', 'mark_reason']
    list_filter = ['is_correct', 'is_marked', 'mark_reason']
    search_fields = ['submission__user__username', 'question__question_text']
    readonly_fields = ['submission', 'question', 'selected_option', 'is_correct']
    
    def submission_user(self, obj):
        return obj.submission.user.username
    submission_user.short_description = 'User'
    
    def question_preview(self, obj):
        return obj.question.question_text[:50] + '...'
    question_preview.short_description = 'Question'


@admin.register(RevisionLog)
class RevisionLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'question_preview', 'reason', 'source_test_card', 'source_submission_attempt', 'added_at']
    list_filter = ['reason', 'source_test_card__test_type', 'added_at']
    search_fields = ['user__username', 'question__question_text']
    date_hierarchy = 'added_at'
    readonly_fields = ['user', 'question', 'reason', 'source_test_card', 'source_submission_attempt', 'added_at']
    
    def question_preview(self, obj):
        return obj.question.question_text[:50] + '...'
    question_preview.short_description = 'Question'
    
    def has_add_permission(self, request):
        return False


# Custom admin actions
@admin.action(description='Reset reward points to 0')
def reset_reward_points(modeladmin, request, queryset):
    queryset.update(reward_points=0)

UserProfileAdmin.actions = [reset_reward_points]