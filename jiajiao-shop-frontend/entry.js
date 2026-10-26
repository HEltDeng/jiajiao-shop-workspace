'use strict';
// Entry codes select a single branch. No merchant directory or external redirect.
function parseShopEntry(input, origin) {
  const value = String(input || '').trim();
  if (/^[a-zA-Z0-9_-]{1,80}$/.test(value)) return value;
  let url;
  try { url = new URL(value, origin); } catch { throw new Error('请输入有效的入口码或小铺链接'); }
  const match = url.pathname.match(/^\/s\/([a-zA-Z0-9_-]{1,80})\/?$/);
  if (url.origin !== origin || url.username || url.password || !match) {
    throw new Error('请输入本平台的小铺入口码或链接');
  }
  return match[1];
}
if (typeof module !== 'undefined') module.exports = {parseShopEntry};
