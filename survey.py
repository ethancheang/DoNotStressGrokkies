"""Evidence questionnaire v3: the wording, chapters and safety patterns.

Source: donotstress_question_evidence.docx, 9 October 2026, section 2.
Every question uses one 1-5 scale except typical sleep, which stays a
0-14 hour slider (half-hour steps) and is converted to 1-5 only when
scoring. logic_manager owns scoring, context flags and tiers. Items are
adapted from their source instruments, so results are NOT PSS-4, PSQI,
IFDFW or MSPSS scores. Positively worded items (reverse=True) are scored
as 6 - answer, so a higher scored value always means more stress. Never
convert legacy /10 or evidence-v2 records onto this scale.

This module holds content only; the behaviour lives in the questions
package (Question, Section, SafetyCheck, Questionnaire).
"""

from questions.question import Question
from questions.questionnaire import Questionnaire
from questions.section import Section

VERSION = "evidence-v3"
SCALE_MIN, SCALE_MAX = 1, 5

PSS_OPTIONS = ("Never", "Almost never", "Sometimes", "Fairly often",
               "Very often")
SLEEP_OPTIONS = ("Very good", "Fairly good", "Okay", "Fairly bad",
                 "Very bad")
AGREE_OPTIONS = ("Strongly disagree", "Disagree", "Neutral", "Agree",
                 "Strongly agree")
FIN_OPTIONS = ("No stress at all", "A little stress", "Moderate stress",
               "High stress", "Overwhelming stress")

# Shared with the browser for an immediate, conservative support prompt.
# Keywords can give false positives/negatives; never claim to assess safety.
SAFETY_PATTERNS = (
    r"\bsuicid(?:e|al)\b",
    r"\bself[ -]?harm(?:ing)?\b",
    r"\b(?:kill|hurt|harm|cut)(?:ing)? myself\b",
    r"\b(?:end|take) my (?:own )?life\b",
    r"\b(?:want|wish|going|plan|planning) to die\b",
    r"\b(?:cannot|can't|dont|don't) "
    r"(?:go on|keep myself safe|want to live)\b",
    r"\bbetter off dead\b",
    r"\b(?:took|taken|take) an overdose\b",
)

QUESTIONNAIRE = Questionnaire(
    VERSION,
    [
        Question(
            "pss_1", "Losing control",
            "In the past month, how often have you felt you couldn't "
            "control the important things in your life?",
            SCALE_MIN, SCALE_MAX, PSS_OPTIONS),
        Question(
            "pss_2", "Handling personal problems",
            "In the past month, how often have you felt confident "
            "handling your personal problems?",
            SCALE_MIN, SCALE_MAX, PSS_OPTIONS, reverse=True),
        Question(
            "pss_3", "Things going your way",
            "In the past month, how often have you felt things were "
            "going well for you?",
            SCALE_MIN, SCALE_MAX, PSS_OPTIONS, reverse=True),
        Question(
            "pss_4", "Difficulties piling up",
            "In the past month, how often have you felt problems were "
            "piling up too much to handle?",
            SCALE_MIN, SCALE_MAX, PSS_OPTIONS),
        Question(
            "sleep_hours_avg", "Typical sleep · past week",
            "On average, how many hours of sleep have you gotten each "
            "night this week?",
            0, 14, step=0.5, kind="slider", default=7, low="0 hours",
            high="14 hours", unit="hours"),
        Question(
            "sleep_quality", "Sleep quality · past week",
            "During the past week, how would you rate your sleep quality "
            "overall?",
            SCALE_MIN, SCALE_MAX, SLEEP_OPTIONS),
        Question(
            "pas_workload", "Study workload",
            "I feel my coursework is too much to handle.",
            SCALE_MIN, SCALE_MAX, AGREE_OPTIONS),
        Question(
            "pas_catchup", "Catching up",
            "When I fall behind on my work, I find it hard to catch up.",
            SCALE_MIN, SCALE_MAX, AGREE_OPTIONS),
        Question(
            "fin_stress", "Personal finances",
            "How stressed do you feel about your personal finances in "
            "general?",
            SCALE_MIN, SCALE_MAX, FIN_OPTIONS, kind="slider", default=3,
            low="No stress at all", high="Overwhelming stress",
            unit="out of 5"),
        Question(
            "mspss_friends", "Support from friends",
            "I can count on my friends when things go wrong.",
            SCALE_MIN, SCALE_MAX, AGREE_OPTIONS, reverse=True),
        Question(
            "mspss_family", "Support from family",
            "I get the emotional help and support I need from my family.",
            SCALE_MIN, SCALE_MAX, AGREE_OPTIONS, reverse=True),
    ],
    [
        Section(
            "Your month", "Start with the bigger picture.",
            "Think about the last month",
            "Notice how manageable life has felt, including moments when "
            "things went well. Choose how often each experience happened.",
            "These four questions explore perceived stress: how "
            "unpredictable, difficult to control, or overwhelming life has "
            "felt. Together they give more context than one stress rating.",
            ("pss_1", "pss_2", "pss_3", "pss_4")),
        Section(
            "Rest & recovery", "How has your sleep been?",
            "Think about the past week",
            "Now zoom in on your recent routine. Think about a typical "
            "night, rather than only last night.",
            "Sleep and stress can affect one another. Hours and quality "
            "capture different parts of rest; either can help explain why "
            "daily demands feel harder to manage.",
            ("sleep_hours_avg", "sleep_quality")),
        Section(
            "Study demands", "Make room for your study load.",
            "Your current study experience",
            "With your overall feelings and rest in mind, consider the "
            "demands of your coursework.",
            "Feeling overloaded by assignments can add pressure and reduce "
            "time for recovery. This question identifies a possible source "
            "of strain, rather than judging your academic performance.",
            ("pas_workload", "pas_catchup")),
        Section(
            "Money pressures", "Life outside the timetable.",
            "Your personal finances in general",
            "Everyday expenses can take up mental space too. You do not "
            "need to share amounts or financial details.",
            "Financial worries may compete for attention alongside study "
            "demands. This question helps us suggest relevant support "
            "without assuming your income or circumstances.",
            ("fin_stress",)),
        Section(
            "Your support", "Who can you lean on?",
            "The support available to you",
            "After looking at pressures, consider the people who help you "
            "face them. Friends and family may support you in different "
            "ways.",
            "Support can make stressful experiences easier to navigate. "
            "These questions look at sources of support; they do not "
            "cancel out or invalidate the stress you reported.",
            ("mspss_friends", "mspss_family")),
        Section(
            "A moment to reflect", "Anything else on your mind?",
            "Optional · not scored",
            "Numbers cannot capture everything. You can reflect here, or "
            "continue without writing anything.",
            "Your reflection does not contribute to the stress score. A "
            "basic safety check can highlight support, but it cannot "
            "recognise every situation. You can contact support at any "
            "time.",
            ()),
    ],
    SAFETY_PATTERNS,
)
