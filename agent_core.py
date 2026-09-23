import asyncio
from typing import Any, Dict
import httpx
from pydantic import BaseModel, Field


class BudgetExceededError(Exception):
  """Исключение при исчерпании лимита токенов/бюджета."""

  pass


class AgentTokenTracker:

  def __init__(self, max_total_tokens: int = 50000):
    self.prompt_tokens = 0
    self.completion_tokens = 0
    self.max_total_tokens = max_total_tokens  # Защита бюджета

  def track(self, usage: dict):
    p_tokens = usage.get("prompt_tokens", 0)
    c_tokens = usage.get("completion_tokens", 0)

    self.prompt_tokens += p_tokens
    self.completion_tokens += c_tokens

    total = self.prompt_tokens + self.completion_tokens
    print(
        f"[LLM Cost Guard] Использовано токенов: {total} /"
        f" {self.max_total_tokens}"
    )

    if total >= self.max_total_tokens:
      raise BudgetExceededError(
          "Превышен лимит токенов! Агент принудительно остановлен для защиты"
          " бюджета."
      )


async def run_autonomous_agent(user_task: str, max_steps: int = 4) -> str:
  """Цикл агента: Observer -> Analysis -> Action с защитой от зацикливания и

  перерасхода.
  """
  tracker = AgentTokenTracker(
      max_total_tokens=40000
  )  # Безопасный порог на задачу
  step = 0

  while step < max_steps:
    step += 1
    print(f"\n--- Шаг агента {step}/{max_steps} ---")

    try:
      # Пример защищенного запроса к LLM (Qwen / OpenAI-compatible API)
      # Важно: всегда передаем max_tokens, чтобы модель не генерировала бесконечный текст
      payload = {
          "model": "qwen-max",  # или ваша рабочая модель
          "messages": [{"role": "user", "content": user_task}],
          "max_tokens": 500,  # Жесткое ограничение длины ответа
      }

      # Симуляция ответа API (на хакатоне здесь будет реальный httpx.post)
      # response = await client.post("https://api.vash-provider.com/v1/chat/completions", json=payload)
      # data = response.json()

      # Имитация расхода токенов ответа API для примера:
      mock_api_usage = {"prompt_tokens": 120, "completion_tokens": 85}

      # Проверяем бюджет по реальным данным из ответа LLM
      tracker.track(mock_api_usage)

      # Здесь логика обработки ответа агента (Action / вызов инструментов Нурлана)
      # Если задача решена, делаем return результата:
      # return "Результат выполнения задачи"

    except BudgetExceededError as e:
      print(f"[ERROR] {e}")
      return (
          "Запрос прерван: достигнут лимит токенов для сохранения бюджета"
          " команды."
      )
    except Exception as e:
      print(f"[WARNING] Ошибка во время шага агента: {e}")
      # Сервер не должен падать с 500 ошибкой, возвращаем мягкий фолбэк
      break

  return "Агент завершил работу по лимиту шагов без финального ответа."