import re

with open('virtual_staff_brain_3_0.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update def signature
content = content.replace('def process_patient_query(raw_query: str, patient_record_text: str = "", patient_id: str = "") -> str:', 'def process_patient_query(raw_query: str, patient_record_text: str = "", patient_id: str = "") -> tuple[str, bool]:')

# 2. Update early returns
content = content.replace('return result_holder[0] if result_holder else ""', 'return result_holder[0] if result_holder else ("", False)')
content = content.replace('if should_skip:\n        return ""', 'if should_skip:\n        return ("", False)')

# 3. Update emergency 1
content = content.replace('holder.append(final_response)', 'holder.append((final_response, True))', 1)
content = content.replace('return final_response', 'return (final_response, True)', 1)

# 4. Update emergency 2
content = content.replace('holder.append(final_response)', 'holder.append((final_response, True))', 1)
content = content.replace('return final_response', 'return (final_response, True)', 1)

# 5. Update symptom followup
content = content.replace('holder.append(symptom_followup)', 'holder.append((symptom_followup, False))')
content = content.replace('return symptom_followup', 'return (symptom_followup, False)')

# 6. Update rule match question
content = content.replace('holder.append(final_response)', 'holder.append((final_response, False))', 1)
content = content.replace('return final_response', 'return (final_response, False)', 1)

# 7. Update quick answer
content = content.replace('holder.append(quick_answer)', 'holder.append((quick_answer, False))')
content = content.replace('return quick_answer', 'return (quick_answer, False)')

# 8. Add is_routed logic
content = content.replace('route_text = ""  # [GUARD]', 'route_text = ""\n    is_routed = False\n    # [GUARD]')
content = content.replace('if decision.is_ready_for_route and len(decision.optimized_route) > 0:', 'if decision.is_ready_for_route and len(decision.optimized_route) > 0:\n                is_routed = True')

# 9. Update final return
content = content.replace('holder.append(tts_response)', 'holder.append((tts_response, is_routed))')
content = content.replace('return tts_response', 'return (tts_response, is_routed)')

# 10. Update __main__
content = content.replace('process_patient_query(user_input, patient_record_text, current_patient_id)', 'resp, routed = process_patient_query(user_input, patient_record_text, current_patient_id)\n                if routed:\n                    print("\\n[HỆ THỐNG] Đã điều hướng xong. Sẵn sàng đón bệnh nhân tiếp theo!")')

with open('virtual_staff_brain_3_0.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("PATCH_DONE")
