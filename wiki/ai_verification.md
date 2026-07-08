# AI-проверка отчётов

## Принцип

После каждого засчитанного отчёта бот запускает `_verify_and_reply` в фоне (`asyncio.create_task`).  
Функция вызывает AI, получает оценку, отправляет реплай на сообщение студента.

## Что проверяется

| Задание | Ключ | Что проверяет AI |
|---|---|---|
| Хадис (h) | `"hadith (arabic word spelling and translation accuracy)"` | Написание арабского слова, точность перевода |
| Таджвид (j) | `"tajweed (mahraj and sifat of letters)"` | Место выхода буквы (махрадж), свойства (сифат) |
| Нахв (n) | `"arabic grammar (nahw/irab)"` | Иъраб (конечная огласовка), название члена предложения |
| Муфрадат (t) | `"mufradat (arabic word spelling and translation accuracy)"` | Написание арабского слова, точность перевода |
| Письмо (всегда при арабском тексте) | авто | Хамза, соединение букв, огласовки, та-марбута, алиф-максура |

## Логика ответа

- AI ответил "CORRECT" или "ВЕРНО" → реплай "✅"
- AI нашёл ошибку → реплай "🤖 Ясир:\n[объяснение]"
- AI не ответил (None) → тишина

## Промпт (английский)

Промпт и системное сообщение — **на английском**. Это критически важно: если промпт на русском, модель путается при генерации кыргызского/узбекского текста.

`lang_instruction(lang)` добавляется в конце системного сообщения — указывает язык ответа на английском:  
`"IMPORTANT: write the ENTIRE response in Kyrgyz language (code: ky). Do not mix languages."`

## Справочник (REFERENCE)

В конце системного промпта прикрепляется `get_full_program_info()` из `core/content.py`.  
AI обязан сверяться со справочником, не с тренировочными данными.  
Правило: если правила нет в справочнике и AI не уверен на 100% — молчит.

## reply_to_message_id

Ответы AI идут реплаем на исходное сообщение студента.  
`message_id` прокинут через стек: `bot.py → queued_process_message → process_message → _verify_and_reply → send_message`.  
`send_message(chat_id, text, reply_to_message_id=None)` — параметр опциональный.  
`allow_sending_without_reply=True` — если исходное сообщение удалено, бот всё равно отправит.

## Сигнатура функции

```python
async def _verify_and_reply(
    chat_id, text, group_title, phone, group_id,
    name, checks, glang="ru", message_id=None
)
```
