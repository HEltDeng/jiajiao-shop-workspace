const {test} = require('node:test');
const assert = require('node:assert/strict');
const {parseShopEntry} = require('../entry.js');
const origin = 'https://jiajiao.mychangliapp.cn';
test('accepts exact branch codes, generated codes, and platform links', () => {
  for (const [input, expected] of [
    [' qinghe ', 'qinghe'], ['a_B-c123', 'a_B-c123'],
    ['/s/qinghe', 'qinghe'], ['/s/qinghe/', 'qinghe'],
    [origin + '/s/qinghe?from=share#top', 'qinghe']
  ]) assert.equal(parseShopEntry(input, origin), expected);
});
test('rejects external sites, credentials, scripts, traversal, and other platform pages', () => {
  for (const input of ['', '   ', 'https://elsewhere.example/s/qinghe',
    '//elsewhere.example/s/qinghe', 'javascript:alert(1)', 'https://user@jiajiao.mychangliapp.cn/s/qinghe',
    '/platform', '/s/qinghe/../../platform', '/s/qinghe/extra', '/s/a%2Fb', 'x'.repeat(81)]) {
    assert.throws(() => parseShopEntry(input, origin), input);
  }
});
