from main.models import Part  # Part 모델을 올바르게 임포트

def part_context(request):
    parts = Part.objects.all().order_by('name')  # 주제 목록 가져오기
    return {'parts': parts}  # 템플릿에서 사용할 수 있도록 반환
