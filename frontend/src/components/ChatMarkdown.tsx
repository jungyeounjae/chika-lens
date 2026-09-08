import Markdown from "react-markdown";

/** 어시스턴트 서술을 마크다운으로 렌더링한다.
 *
 * LLM 은 지시하지 않아도 `**보육·교육 24곳**` 처럼 마크다운으로 쓴다. 평문으로
 * 흘리면 별표가 그대로 보이고, 프롬프트로 "마크다운 쓰지 마"라고 막으면 목록과
 * 강조를 잃는다 — 지표 다섯 개를 나열하는 답변에서 그 구조가 가독성의 대부분이다.
 *
 * 스트리밍 중에는 마크다운이 미완성이다 (`**공원` 처럼 닫히지 않은 상태).
 * react-markdown 은 그런 조각을 글자 그대로 보여주고, 닫히는 순간 강조로 바뀐다.
 *
 * HTML 은 통과시키지 않는다 (rehype-raw 를 넣지 않았다). LLM 출력은 사용자
 * 입력이 섞인 결과물이므로 태그를 살려줄 이유가 없다.
 */
export function ChatMarkdown({ text }: { text: string }) {
  return (
    <div
      className={
        // prose 의 기본 여백은 문서용이라 대화에서는 지나치게 넓다.
        "prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed " +
        "prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 " +
        "prose-headings:mt-3 prose-headings:mb-1 prose-headings:text-sm " +
        // 역명(北千住)이 굵게 나올 때 본문과 같은 색이어야 읽힌다.
        "prose-strong:text-inherit prose-strong:font-semibold " +
        // 표는 지도 옆 절반 폭을 넘길 수 있다. 본문이 밀리지 않게 가둔다.
        "prose-table:my-2 prose-table:block prose-table:overflow-x-auto"
      }
    >
      <Markdown
        components={{
          // 링크를 낼 이유가 없다. 냈다면 새 탭으로, 참조는 끊어서.
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}
