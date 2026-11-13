from app.models.agent_task import AgentTask
from app.models.ai_usage import AiDailyUsage
from app.models.audit_log import AuditLog
from app.models.portfolio import Portfolio, PortfolioDomainTag, PortfolioEvidence
from app.models.school import School, SchoolDepartmentLink
from app.models.award_record import SchoolAwardRecord
from app.models.certificate import AwardCertificate
from app.models.project import (
    ProjectGroup,
    ProjectMember,
    ProjectType,
    RequirementItem,
    RequirementTemplate,
    StudentProjectAssignment,
)
from app.models.submission import PortfolioGoalSnapshot, PortfolioSubmission, SubmissionEvidence
from app.models.review import ProjectReviewResult, ProjectRevisionRecord, SubmissionAssignment, TeacherReviewFeedback
from app.models.learning_profile import (
    CourseRule,
    CredentialRecord,
    DocumentExtraction,
    LearningCourseRecord,
    LearningProfileOutput,
    SourceDocument,
)
from app.models.user import StudentProfile, User, UserBackupCode
from app.models.admission import (
    AdmissionEligibilityRule,
    AdmissionProgram,
    AdmissionRequirementItem,
    AdmissionRuleItemCategory,
    AdmissionScheduleEvent,
    ClassAdvisor,
    PackageReview,
    StudentTarget,
)
from app.models.p0_workbench import (
    ConsentRecord,
    PuzzlePiece,
    PuzzleEvidence,
    EditableDraft,
    ApiKeyMetadata,
    PublicSource,
    PublicSourceSnapshot,
    PublicSourceChange,
    PublicSourcePublication,
)
from app.models.transfer_credit import TransferCreditRecord
from app.models.system_setting import SystemSetting
from app.models.google_doc import AutobiographyGoogleDoc, StudentDriveFolder
from app.models.match_filter import MatchFilterOption
from app.models.graduation_case import GraduationCase, GraduationCaseEvent, Notification
from app.models.form_library import FormCategory, FormItem, FormItemVersion
from app.models.curriculum import CurriculumCourse, CurriculumVersion

__all__ = [
    "AiDailyUsage",
    "AwardCertificate",
    "SchoolAwardRecord",
    "AgentTask",
    "AuditLog",
    "Portfolio",
    "PortfolioEvidence",
    "StudentProfile",
    "User",
    "ProjectType",
    "RequirementTemplate",
    "RequirementItem",
    "ProjectGroup",
    "ProjectMember",
    "StudentProjectAssignment",
    "PortfolioSubmission",
    "PortfolioGoalSnapshot",
    "SubmissionEvidence",
    "SubmissionAssignment",
    "TeacherReviewFeedback",
    "ProjectReviewResult",
    "ProjectRevisionRecord",
    "SourceDocument",
    "DocumentExtraction",
    "LearningCourseRecord",
    "CourseRule",
    "CredentialRecord",
    "LearningProfileOutput",
    "ConsentRecord",
    "PuzzlePiece",
    "PuzzleEvidence",
    "EditableDraft",
    "ApiKeyMetadata",
    "PublicSource",
    "PublicSourceSnapshot",
    "PublicSourceChange",
    "PublicSourcePublication",
    "AdmissionProgram",
    "AdmissionEligibilityRule",
    "AdmissionRequirementItem",
    "AdmissionRuleItemCategory",
    "PortfolioDomainTag",
    "School",
    "SchoolDepartmentLink",
    "AdmissionScheduleEvent",
    "StudentTarget",
    "ClassAdvisor",
    "PackageReview",
    "TransferCreditRecord",
    "SystemSetting",
    "AutobiographyGoogleDoc",
    "StudentDriveFolder",
    "MatchFilterOption",
    "GraduationCase",
    "GraduationCaseEvent",
    "Notification",
    "FormCategory",
    "FormItem",
    "FormItemVersion",
    "CurriculumVersion",
    "CurriculumCourse",
    "UserBackupCode",
]
