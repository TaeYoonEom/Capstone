from django.core.management.base import BaseCommand
from django.db import transaction
from django.apps import apps
from main.models import Paper, PaperEmbedding
import torch, time

BATCH = 64
MAXLEN = 256

class Command(BaseCommand):
    help = "Generate/refresh CLS embeddings for all papers with batched inference and bulk upserts."

    def handle(self, *args, **options):
        cfg = apps.get_app_config('main')
        tokenizer = cfg.tokenizer
        model = cfg.model

        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        model.eval().to(device)

        total = Paper.objects.count()
        if total == 0:
            self.stdout.write("⚠️ No papers found. Exiting...")
            return

        # id, title, abstract만 스트리밍으로 읽기 (메모리 절약)
        rows = Paper.objects.values_list('id', 'title', 'abstract').iterator(chunk_size=1000)

        # 기존 임베딩 매핑(업서트 대비)
        existing = {e.paper_id: e for e in PaperEmbedding.objects.all().only('paper_id')}

        start = time.time()
        buf_ids, buf_texts = [], []
        processed = 0

        def flush_batch():
            nonlocal processed
            if not buf_ids:
                return

            # 배치 토크나이즈/추론
            inputs = tokenizer(
                buf_texts,
                return_tensors='pt',
                padding=True,
                truncation=True,
                max_length=MAXLEN
            ).to(device)

            with torch.no_grad():
                out = model(**inputs).last_hidden_state[:, 0, :]  # CLS

            # 저장 최적화: fp16으로 축소
            vecs = out.detach().cpu().to(torch.float16).numpy()

            new_objs, upd_objs = [], []
            for pid, v in zip(buf_ids, vecs):
                vec_list = v.tolist()
                if pid in existing:
                    obj = existing[pid]
                    obj.vector = vec_list
                    upd_objs.append(obj)
                else:
                    new_objs.append(PaperEmbedding(paper_id=pid, vector=vec_list))

            # 벌크 트랜잭션
            with transaction.atomic():
                if new_objs:
                    PaperEmbedding.objects.bulk_create(new_objs, batch_size=512, ignore_conflicts=True)
                if upd_objs:
                    PaperEmbedding.objects.bulk_update(upd_objs, ['vector'], batch_size=512)

            processed += len(buf_ids)
            elapsed = time.time() - start
            self.stdout.write(f"✅ Processed {processed}/{total} (elapsed {elapsed:.1f}s)")

            buf_ids.clear()
            buf_texts.clear()

        for pid, title, abstract in rows:
            text = f"{title or ''} {abstract or ''}".strip() or "[EMPTY]"
            buf_ids.append(pid)
            buf_texts.append(text)
            if len(buf_ids) >= BATCH:
                flush_batch()

        flush_batch()
        self.stdout.write(self.style.SUCCESS(f"🎉 Paper embeddings updated for {processed}/{total} in {time.time()-start:.1f}s"))
