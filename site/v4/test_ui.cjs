const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const html=fs.readFileSync("site/v4/index.html","utf8");
const blocks=[...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
assert.equal(blocks.length,1,"One self-contained client-side renderer");
new vm.Script(blocks[0][1],{filename:"site/v4/index.html"});
for(const text of ["실제로 무엇이 변경됐나",
                  "변경 기준을 적용하는 다른 규정",
                  "공식 위임 관계에 있는 추가 검토 규정",
                  "기관별 업무 영향",
                  "신구 조문 확인",
                  "전체 공식 목록"]){
  assert.ok(html.includes(text),"Missing required evidence stage: "+text);
}
assert.match(html,/d\.schema|DATA\.schema/);
assert.match(html,/escape|ESC\(/);
assert.match(html,/implementation_verified|내부 조치/);
console.log("PASS: V4 impact-first renderer, source/causality separation, and HTML JavaScript");
