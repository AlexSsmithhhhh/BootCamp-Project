from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable


SYSTEM_GAP = "system"
ROUTINE_GAP = "routine"
JOURNAL_GAP = "journal"
EXECUTION_GAP = "execution"
PSYCHOLOGY_GAP = "psychology"
NO_GAP = "no_gap"

PROBLEM_CATEGORIES = (
    SYSTEM_GAP,
    ROUTINE_GAP,
    JOURNAL_GAP,
    EXECUTION_GAP,
    PSYCHOLOGY_GAP,
)
CATEGORIES = (*PROBLEM_CATEGORIES, NO_GAP)

CATEGORY_LABELS = {
    SYSTEM_GAP: "System Gap",
    ROUTINE_GAP: "Routine Gap",
    JOURNAL_GAP: "Journal Gap",
    EXECUTION_GAP: "Execution Gap",
    PSYCHOLOGY_GAP: "Psychology Gap",
    NO_GAP: "No Gap",
}

RESULT_TAGS = {
    SYSTEM_GAP: "system_gap",
    ROUTINE_GAP: "routine_gap",
    JOURNAL_GAP: "journal_gap",
    EXECUTION_GAP: "execution_gap",
    PSYCHOLOGY_GAP: "psychology_gap",
    NO_GAP: "no_gap",
}

ANSWER_DISPLAY_LABELS = {
    "A": "1",
    "B": "2",
    "C": "3",
    "D": "4",
    "E": "5",
    "F": "6",
}


@dataclass(frozen=True)
class QuizOption:
    key: str
    text: str
    category: str


@dataclass(frozen=True)
class QuizQuestion:
    text: str
    options: tuple[QuizOption, ...]


@dataclass(frozen=True)
class QuizResult:
    key: str
    title: str
    message: str


@dataclass(frozen=True)
class QuizOutcome:
    result_key: str
    scores: dict[str, int]
    tied_categories: tuple[str, ...]


def _options(
    *,
    system: str,
    routine: str,
    journal: str,
    execution: str,
    psychology: str,
    no_gap: str,
) -> tuple[QuizOption, ...]:
    return (
        QuizOption("A", system, SYSTEM_GAP),
        QuizOption("B", routine, ROUTINE_GAP),
        QuizOption("C", journal, JOURNAL_GAP),
        QuizOption("D", execution, EXECUTION_GAP),
        QuizOption("E", psychology, PSYCHOLOGY_GAP),
        QuizOption("F", no_gap, NO_GAP),
    )


QUIZ_QUESTIONS = (
    QuizQuestion(
        "Что лучше всего описывает твою торговлю сейчас?",
        _options(
            system=(
                "Я торгую разные сетапы и идеи, которые часто зависят от мнения "
                "в комьюнити или Telegram-каналах."
            ),
            routine=(
                "Моя торговля выглядит так: поверхностный анализ рынка → вход "
                "в позицию или ожидание входа → стоп/тейк → Repeat."
            ),
            journal="Я редко разбираю сделки и не понимаю, какие выводы из них делать.",
            execution=(
                "У меня есть правила и факторы входа в позицию, но я часто нарушаю "
                "их в моменте."
            ),
            psychology=(
                "Я подвержен эмоциональному трейдингу: FOMO, страх, злость, желание "
                "отыграться, овертрейдинг."
            ),
            no_gap="Стабильно показываю удовлетворительные результаты.",
        ),
    ),
    QuizQuestion(
        "Что чаще всего происходит перед входом в сделку?",
        _options(
            system="Я не всегда понимаю, какие условия должны совпасть для качественного входа.",
            routine=(
                "Я не формирую планы на день и нахожусь у графиков большую часть дня."
            ),
            journal="Я не фиксирую причины и результаты входа в сделку.",
            execution=(
                "Я могу войти раньше времени, хотя понимаю, что подтверждения ещё нет."
            ),
            psychology="Я часто боюсь упустить движение и вхожу под влиянием FOMO.",
            no_gap=(
                "У меня есть сформированный план и четкий сетап. Я придерживаюсь их "
                "и не ощущаю напряжения, когда пропускаю вход."
            ),
        ),
    ),
    QuizQuestion(
        "Как ты обычно оцениваешь результат сделки?",
        _options(
            system=(
                "Смотрю в основном на прибыль или убыток, но не всегда понимаю причины "
                "и качество своих решений."
            ),
            routine=(
                "У меня нет стабильного процесса закрытия торговой сессии и анализа "
                "дня/недели."
            ),
            journal="Я не веду торговый журнал или веду его нерегулярно.",
            execution="Даже если сделка была по плану, я могу вносить коррективы в моменте.",
            psychology="После убытка мне сложно оставаться спокойным и контролировать себя.",
            no_gap="Веду журнал и регулярно провожу анализ.",
        ),
    ),
    QuizQuestion(
        "Что чаще всего мешает тебе улучшать результат?",
        _options(
            system="Я не понимаю, какой элемент торговли нужно улучшать.",
            routine=(
                "У меня нет повторяемого процесса: каждый день проходит по-разному, "
                "а каждая сделка имеет разные причины входа."
            ),
            journal=(
                "У меня мало данных по своим сделкам, поэтому выводы получаются "
                "на ощущениях."
            ),
            execution=(
                "Я вижу свои ошибки, но продолжаю повторять их из сделки к сделке."
            ),
            psychology=(
                "Я слишком эмоционально реагирую на серию убытков или упущенные сделки."
            ),
            no_gap="Ничего не мешает.",
        ),
    ),
    QuizQuestion(
        "Как ты понимаешь, что твоя стратегия реально работает?",
        _options(
            system="По ощущениям.",
            routine=(
                "Я не всегда торгую в одинаковых условиях, поэтому сложно оценить "
                "объективно."
            ),
            journal="У меня нет достаточной статистики по сетапам, ошибкам и результатам.",
            execution="Я не всегда исполняю стратегию так, как она была задумана.",
            psychology="Я могу начать сомневаться в себе после нескольких минусов подряд.",
            no_gap=(
                "Я регулярно веду торговый журнал или дневник, провожу анализ "
                "и периодически возвращаюсь к старым сделкам."
            ),
        ),
    ),
    QuizQuestion(
        "Что происходит, когда рынок идёт не по твоему сценарию?",
        _options(
            system="Я не всегда заранее понимаю, где моя идея становится невалидной.",
            routine="У меня нет заранее прописанного плана действий на разные сценарии.",
            journal="Я не фиксирую, как часто мои сценарии не отрабатывают.",
            execution=(
                "Я могу передвинуть стоп, увеличить риск или перезайти в позицию."
            ),
            psychology=(
                "Я начинаю злиться, торопиться или пытаться срочно вернуть убыток."
            ),
            no_gap="Я принимаю всё так, как происходит.",
        ),
    ),
    QuizQuestion(
        "Что тебе сейчас больше всего нужно для прогресса?",
        _options(
            system="Собрать торговлю в понятную систему с чёткими компонентами.",
            routine="Выстроить стабильную рутину подготовки, торговли и анализа.",
            journal="Научиться вести журнал и делать выводы из своих действий.",
            execution="Улучшить исполнение правил в реальных сделках.",
            psychology="Научиться лучше управлять эмоциями и поведением в рынке.",
            no_gap="Я прогрессирую, и это подтверждает мой торговый журнал.",
        ),
    ),
)

QUIZ_RESULTS = {
    SYSTEM_GAP: QuizResult(
        SYSTEM_GAP,
        "Твоя проблема — торговая система",
        (
            "<b>Твоя проблема — торговая система.</b>\n\n"
            "Это значит, что твоя торговля может состоять из отдельных элементов: "
            "сетапов, идей, наблюдений, риск-менеджмента или фрагментов стратегии, "
            "но пока они не собраны в цельную систему.\n\n"
            "Проблема не обязательно в недостатке знаний. Скорее всего, знания уже "
            "есть, но они не связаны в единый понятный процесс:\n"
            "• как ты читаешь контекст рынка;\n"
            "• какой сетап торгуешь;\n"
            "• какие условия нужны для входа;\n"
            "• где идея становится невалидной;\n"
            "• как фиксируется сделка;\n"
            "• как потом делается ревью."
        ),
    ),
    ROUTINE_GAP: QuizResult(
        ROUTINE_GAP,
        "Твоя проблема — торговая рутина",
        (
            "<b>Твоя проблема — торговая рутина.</b>\n\n"
            "Проблема может быть не в стратегии, а в отсутствии стабильного процесса "
            "вокруг торговли.\n\n"
            "Чаще всего это проявляется так:\n"
            "• общий хаос в торговле;\n"
            "• нет подготовки перед сессией;\n"
            "• нет списка активов для фокуса;\n"
            "• нет планов на день;\n"
            "• решения принимаются в моменте;\n"
            "• сделки фиксируются нерегулярно."
        ),
    ),
    JOURNAL_GAP: QuizResult(
        JOURNAL_GAP,
        "Твоя проблема — отсутствие торгового журнала",
        (
            "<b>Твоя проблема — отсутствие торгового журнала.</b>\n\n"
            "Весь получаемый в рынке опыт упускается.\n\n"
            "Представь, что в TradingView вся свечная информация исчезала бы через "
            "час после появления следующей свечи. Как анализировать рынок и торговать?\n\n"
            "В таком режиме трейдер не то, что будет повторять одни и те же ошибки, "
            "но вся торговля превратиться в бесконтрольный, абстрактный процесс."
        ),
    ),
    EXECUTION_GAP: QuizResult(
        EXECUTION_GAP,
        "Твоя проблема — реализация",
        (
            "<b>Твоя проблема — реализация.</b>\n\n"
            "Одна из самых частых проблем в трейдинге — отклонение от собственных "
            "правил и плана.\n\n"
            "Причин этому может быть множество: от недостатка теоретических знаний "
            "или опыта, до психологии."
        ),
    ),
    PSYCHOLOGY_GAP: QuizResult(
        PSYCHOLOGY_GAP,
        "Твоя проблема — психологическая устойчивость",
        (
            "<b>Твоя проблема — психологическая устойчивость.</b>\n\n"
            "В моменты рыночного давления эмоциональное состояние может брать верх "
            "над заранее прописанным планом.\n\n"
            "В такие периоды решения начинают приниматься не из структуры, а из "
            "импульса: желания отыграться, страха упустить движение, тревоги после "
            "убытка, внутреннего напряжения или внешних раздражителей.\n\n"
            "Важно понимать, что подобные реакции не говорят о слабом характере. "
            "Чаще всего они возникают тогда, когда у трейдера недостаточно опоры "
            "в системе. Если нет понятной рутины, правил исполнения и регулярного "
            "разбора действий."
        ),
    ),
    NO_GAP: QuizResult(
        NO_GAP,
        "Твой результат — Сформированный фундамент",
        (
            "<b>Твой результат — Сформированный фундамент.</b>\n\n"
            "Судя по ответам, у тебя уже есть достаточно сильная база в торговле.\n"
            "Твой трейдинг выглядит более структурно и профессионально, чем у большинства трейдеров.\n\n"
            "Это хороший показатель. Однако трейдинг — это постоянный поиск, самокопание и адаптация. "
            "Как рынок сильно изменчив, так и трейдер должен оставаться гибким и уметь вовремя "
            "реагировать на эти изменения.\n\n"
            "Поэтому важно регулярно проводить анализ актуального уровня и результатов.\n\n"
            "<b>Главная задача BootCamp Open Week — помочь тебе увидеть себя 🧠</b>\n\n"
            "На BootCamp Open Week ты сможешь сверить свой подход с методологией Cryptomann Academy "
            "и посмотреть, насколько твоя система действительно собрана: стратегия, рутина, риск, "
            "execution, журнал и review.\n\n"
            "Даже если у тебя всё неплохо, эта неделя поможет точнее увидеть, что можно улучшить "
            "и какие элементы стоит докрутить.\n\n"
            "С 1 по 5 июня мы открываем закрытый Discord-сервер, где ты сможешь пройти "
            "неделю вместе с Cryptomann Academy.\n\n"
            "<b>Вводи свой номер и присоединяйся к серверу 👇🏻</b>"
        ),
    ),
}


def question_count() -> int:
    return len(QUIZ_QUESTIONS)


def get_question(question_index: int) -> QuizQuestion:
    return QUIZ_QUESTIONS[question_index]


def get_option(question_index: int, answer_key: str) -> QuizOption:
    normalized_key = answer_key.upper()
    for option in get_question(question_index).options:
        if option.key == normalized_key:
            return option
    raise ValueError(f"Unknown answer {answer_key!r} for question {question_index}")


def answer_display_label(answer_key: str) -> str:
    return ANSWER_DISPLAY_LABELS.get(answer_key.upper(), answer_key)


def format_question(question_index: int) -> str:
    question = get_question(question_index)
    options = "\n\n".join(
        f"<b>{answer_display_label(option.key)}.</b> {option.text}"
        for option in question.options
    )
    return (
        f"<b>Вопрос {question_index + 1} из {question_count()}</b>\n\n"
        f"{question.text}\n\n"
        "<b>Варианты ответа:</b>\n\n"
        f"{options}\n\n"
        "Нажми номер ответа ниже."
    )


def score_quiz(answers: Iterable[dict[str, object]]) -> QuizOutcome:
    normalized_answers = list(answers)
    scores = {category: 0 for category in CATEGORIES}
    counter = Counter(str(answer["category"]) for answer in normalized_answers)
    for category in CATEGORIES:
        scores[category] = counter[category]

    max_score = max(scores.values(), default=0)
    if max_score == 0:
        return QuizOutcome(NO_GAP, scores, (NO_GAP,))

    tied = tuple(category for category in CATEGORIES if scores[category] == max_score)
    if len(tied) == 1:
        return QuizOutcome(tied[0], scores, tied)

    actionable_tied = tuple(category for category in tied if category != NO_GAP)
    if not actionable_tied:
        return QuizOutcome(NO_GAP, scores, tied)

    progress_answer = next(
        (
            str(answer["category"])
            for answer in normalized_answers
            if int(answer["question_index"]) == question_count() - 1
        ),
        None,
    )
    if progress_answer in actionable_tied:
        return QuizOutcome(progress_answer, scores, tied)

    for answer in reversed(normalized_answers):
        category = str(answer["category"])
        if category in actionable_tied:
            return QuizOutcome(category, scores, tied)

    return QuizOutcome(actionable_tied[0], scores, tied)


def result_for_key(result_key: str) -> QuizResult:
    return QUIZ_RESULTS[result_key]


def tag_for_result(result_key: str) -> str:
    return RESULT_TAGS[result_key]


def format_score_summary(scores: dict[str, int]) -> str:
    visible_scores = [
        f"• {CATEGORY_LABELS[category]}: <b>{scores.get(category, 0)}</b>"
        for category in CATEGORIES
    ]
    return "\n".join(visible_scores)
