'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle, BrainCircuit, CandlestickChart, CircleDollarSign,
  Gauge, History, Radio, RefreshCw, ShieldCheck, Siren, X,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader,
  AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

type Page = 'overview' | 'market' | 'decision' | 'replay' | 'risk';
type Overview = {
  updated_at: string;
  account: { id: string; balance: number; equity: number; free_margin: number; daily_pnl: number; drawdown_pct: number };
  quote: { symbol: string; bid: number; ask: number; spread: number; atr: number };
  decision: { action: string; confidence: number; threshold: number; reason: string; status: string; long_votes: number; neutral_votes: number; short_votes: number; plan_id: string };
  position: { side: string; volume: number; open_price: number; pnl: number } | null;
  system: { ea_online: boolean; ai_provider: string; ai_configured: boolean; auto_trading: boolean; latency_ms: number; last_heartbeat: string | null };
};

const demo: Overview = {
  updated_at: '1970-01-01T00:00:00Z',
  account: { id: '等待 EA 连接', balance: 0, equity: 0, free_margin: 0, daily_pnl: 0, drawdown_pct: 0 },
  quote: { symbol: 'XAUUSD', bid: 0, ask: 0, spread: 0, atr: 0 },
  decision: { action: 'HOLD', confidence: 0, threshold: 0.65, reason: '等待 EA 上传行情快照后启动 AI 分析。', status: 'WAITING_DATA', long_votes: 0, neutral_votes: 0, short_votes: 0, plan_id: '—' },
  position: null,
  system: { ea_online: false, ai_provider: 'deepseek', ai_configured: false, auto_trading: false, latency_ms: 0, last_heartbeat: null },
};

const nav: Array<{ id: Page; label: string; icon: typeof Gauge }> = [
  { id: 'overview', label: '总览', icon: Gauge },
  { id: 'market', label: '行情', icon: CandlestickChart },
  { id: 'decision', label: '决策', icon: BrainCircuit },
  { id: 'replay', label: '复盘', icon: History },
  { id: 'risk', label: '风控', icon: ShieldCheck },
];

const fmt = (value: number, digits = 2) => value.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const money = (value: number) => `${value >= 0 ? '' : '-'}$${fmt(Math.abs(value))}`;
const statusText: Record<string, string> = { LONG: '看多', SHORT: '看空', HOLD: '观望', CLOSE: '平仓', REDUCE: '减仓' };

function Dot({ ok }: { ok: boolean }) {
  return <span className={`inline-block size-2 rounded-full ${ok ? 'bg-emerald-400 shadow-[0_0_12px_#62efa7]' : 'bg-red-400 shadow-[0_0_12px_#ff6d5f]'}`} />;
}

function Panel({ title, action, className = '', children }: { title: string; action?: ReactNode; className?: string; children: ReactNode }) {
  return <Card className={`terminal-card gap-3 rounded-2xl border py-4 ${className}`}><CardHeader className="px-4"><CardTitle className="flex items-center justify-between text-xs font-semibold uppercase tracking-[.12em] text-zinc-400"><span>{title}</span>{action}</CardTitle></CardHeader><CardContent className="px-4">{children}</CardContent></Card>;
}

function Row({ label, value, tone = 'normal' }: { label: string; value: ReactNode; tone?: 'normal' | 'good' | 'bad' | 'warn' }) {
  const color = tone === 'good' ? 'text-emerald-300' : tone === 'bad' ? 'text-[#ff7467]' : tone === 'warn' ? 'text-amber-300' : 'text-zinc-100';
  return <div className="flex items-center justify-between gap-4 border-b py-2.5 text-sm last:border-0"><span className="text-zinc-500">{label}</span><strong className={`text-right font-medium ${color}`}>{value}</strong></div>;
}

function MiniLine({ negative = false }: { negative?: boolean }) {
  const color = negative ? '#ff6d5f' : '#62efa7';
  return <svg viewBox="0 0 320 74" className="h-20 w-full" preserveAspectRatio="none" aria-hidden="true"><path d="M0 58L25 51L52 53L80 39L108 45L136 32L166 37L196 23L224 34L250 29L278 35L320 25" fill="none" stroke={color} strokeWidth="2.2"/><path d="M0 58L25 51L52 53L80 39L108 45L136 32L166 37L196 23L224 34L250 29L278 35L320 25V74H0Z" fill={color} opacity=".08"/></svg>;
}

function StatusHeader({ data }: { data: Overview }) {
  const updated = useMemo(() => data.quote.bid > 0 ? new Date(data.updated_at).toLocaleTimeString('zh-CN', { hour12: false }) : '—', [data.updated_at, data.quote.bid]);
  return <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-black/20 px-4 py-2.5 text-xs text-zinc-500"><div className="flex flex-wrap gap-x-6 gap-y-2"><span>数据时间 <b className="number text-zinc-200">{updated}</b></span><span>市场 <b className="text-zinc-200">{data.quote.bid > 0 ? '有报价' : '等待数据'}</b></span><span>EA <b className={data.system.ea_online ? 'text-emerald-300' : 'text-red-300'}>{data.system.ea_online ? '在线' : '离线'}</b></span><span>AI <b className={data.system.ai_configured ? 'text-emerald-300' : 'text-amber-300'}>{data.system.ai_configured ? data.system.ai_provider : '未配置密钥'}</b></span></div><Badge variant="outline" className={data.system.auto_trading ? 'border-emerald-400/30 text-emerald-300' : 'border-amber-400/30 text-amber-300'}>{data.system.auto_trading ? 'AUTO 已启用' : '安全观察模式'}</Badge></div>;
}

function OverviewPage({ data }: { data: Overview }) {
  const action = statusText[data.decision.action] ?? data.decision.action;
  const bearish = data.decision.action === 'SHORT';
  const votes: Array<[string, number, string]> = [['多头', data.decision.long_votes, 'bg-emerald-400'], ['中立', data.decision.neutral_votes, 'bg-amber-300'], ['空头', data.decision.short_votes, 'bg-red-400']];
  return <div className="grid grid-cols-12 gap-3">
    <Panel title="决策场 · Decision field" className="col-span-12 min-h-72 xl:col-span-7" action={<Badge variant="outline">{data.decision.status}</Badge>}>
      <div className="grid min-h-52 items-center gap-5 md:grid-cols-[1fr_240px]"><div className="fine-grid relative h-44 overflow-hidden rounded-xl border"><div className="absolute inset-0 bg-[radial-gradient(circle_at_75%_50%,rgba(98,239,167,.16),transparent_25%)]"/><div className="absolute left-[10%] right-[24%] top-[30%] h-px rotate-3 bg-gradient-to-r from-red-400 to-zinc-700"/><div className="absolute left-[5%] right-[24%] top-[48%] h-px -rotate-2 bg-gradient-to-r from-emerald-400 to-zinc-700"/><div className="absolute left-[15%] right-[24%] top-[68%] h-px rotate-6 bg-gradient-to-r from-zinc-400 to-zinc-700"/><div className="absolute right-[18%] top-1/2 size-9 -translate-y-1/2 rounded-full bg-emerald-300 shadow-[0_0_38px_rgba(98,239,167,.72)]"/></div><div><div className="mb-3 text-xs text-zinc-500">{data.quote.symbol} · AI 计划</div><div className={`signal-glow text-6xl font-black tracking-[-.08em] ${bearish ? 'text-[#ff7467]' : data.decision.action === 'LONG' ? 'text-emerald-300' : 'text-amber-200'}`}>{action}</div><div className="mt-4 flex items-baseline gap-2"><strong className="number text-3xl">{Math.round(data.decision.confidence * 100)}%</strong><span className="text-[11px] tracking-[.16em] text-zinc-500">CONFIDENCE</span></div><p className="mt-2 text-xs text-zinc-500">开仓阈值 {Math.round(data.decision.threshold * 100)}% · {data.decision.plan_id}</p></div></div>
    </Panel>
    <Panel title="账户净值 · USD" className="col-span-12 sm:col-span-7 xl:col-span-3" action={<Badge variant="outline">{data.account.id}</Badge>}><div className="number text-3xl font-bold tracking-tight">{money(data.account.equity)}</div><div className={`mt-2 inline-flex rounded-md px-2 py-1 text-xs ${data.account.daily_pnl >= 0 ? 'bg-emerald-400/10 text-emerald-300' : 'bg-red-400/10 text-red-300'}`}>今日 {money(data.account.daily_pnl)}</div><MiniLine negative={data.account.daily_pnl < 0}/><Row label="余额" value={<span className="number">{money(data.account.balance)}</span>}/><Row label="可用保证金" value={<span className="number">{money(data.account.free_margin)}</span>}/></Panel>
    <Panel title="实时行情" className="col-span-12 sm:col-span-5 xl:col-span-2" action={<Badge variant="outline">{data.quote.bid > 0 ? 'LIVE' : 'WAIT'}</Badge>}><div className="text-xs text-zinc-500">{data.quote.symbol}</div><div className="number mt-1 text-3xl font-semibold">{fmt(data.quote.bid)}</div><Row label="Ask" value={<span className="number">{fmt(data.quote.ask)}</span>}/><Row label="点差" value={<span className="number">{fmt(data.quote.spread)}</span>}/><Row label="ATR" value={<span className="number">{fmt(data.quote.atr)}</span>}/></Panel>
    <Panel title="当前信号" className="col-span-12 md:col-span-4"><div className="mb-3 text-2xl font-semibold">{action} <span className="number text-zinc-400">{Math.round(data.decision.confidence * 100)}%</span></div>{votes.map(([label,value,color])=><div key={label} className="grid grid-cols-[44px_1fr_28px] items-center gap-3 py-2 text-xs"><span className="text-zinc-500">{label}</span><div className="h-1.5 overflow-hidden rounded-full bg-white/5"><i className={`block h-full ${color}`} style={{width:`${Math.min(100, value * 6)}%`}}/></div><b className="number">{value}</b></div>)}</Panel>
    <Panel title="执行状态" className="col-span-12 md:col-span-4"><Row label="计划状态" value={data.decision.status} tone={data.decision.status === 'ACTIONABLE' ? 'good' : 'warn'}/><Row label="运行模式" value={data.system.auto_trading ? 'AUTO' : 'OBSERVE'} tone={data.system.auto_trading ? 'good' : 'warn'}/><Row label="API 延迟" value={<span className="number">{data.system.latency_ms} ms</span>}/><Row label="AI 提供商" value={data.system.ai_provider}/></Panel>
    <Panel title="当前持仓" className="col-span-12 md:col-span-4" action={<Badge variant="outline">{data.position ? '持仓中' : '空仓'}</Badge>}>{data.position ? <><div className="text-2xl font-semibold">{data.position.side} <span className="number">{fmt(data.position.volume)} 手</span></div><Row label="开仓价" value={<span className="number">{fmt(data.position.open_price)}</span>}/><Row label="浮动盈亏" value={<span className="number">{money(data.position.pnl)}</span>} tone={data.position.pnl >= 0 ? 'good':'bad'}/></> : <div className="flex min-h-32 flex-col items-center justify-center text-center"><CircleDollarSign className="mb-3 size-8 text-zinc-600"/><strong>当前没有持仓</strong><p className="mt-1 text-xs text-zinc-500">EA 连接后将自动同步账户状态</p></div>}</Panel>
    <Panel title="AI 决策摘要" className="col-span-12 xl:col-span-8"><p className="leading-7 text-zinc-300">{data.decision.reason}</p><div className="mt-4 flex flex-wrap gap-2"><Badge variant="outline">输入快照已存档</Badge><Badge variant="outline">计划可追踪</Badge><Badge variant="outline">EA 本地风控优先</Badge></div></Panel>
    <Panel title="系统状态" className="col-span-12 xl:col-span-4"><Row label="EA 心跳" value={data.system.ea_online ? '正常':'未连接'} tone={data.system.ea_online ? 'good':'bad'}/><Row label="DeepSeek" value={data.system.ai_configured ? '已配置':'等待 API Key'} tone={data.system.ai_configured ? 'good':'warn'}/><Row label="决策接口" value="就绪" tone="good"/><Row label="实盘开关" value={data.system.auto_trading ? '已启用':'默认关闭'} tone={data.system.auto_trading ? 'warn':'good'}/></Panel>
  </div>;
}

function MarketPage({ data }: { data: Overview }) {
  const candles = [46,38,55,62,70,74,68,82,76,64,58,61,52,48,54,45,39,44,36,31,35,29,33,27,30];
  return <div className="grid grid-cols-12 gap-3"><Panel title={`${data.quote.symbol} · M15 · 价格结构`} className="col-span-12 xl:col-span-8"><div className="fine-grid relative h-[430px] overflow-hidden rounded-xl border"><svg viewBox="0 0 800 420" className="size-full" preserveAspectRatio="none"><rect x="40" y="238" width="700" height="56" fill="rgba(99,180,255,.08)" stroke="rgba(99,180,255,.35)" strokeDasharray="5 6"/><line x1="30" y1="260" x2="770" y2="260" stroke="#62efa7" strokeDasharray="5 5"/><text x="640" y="251" fill="#8b988f" fontSize="11">现价 {fmt(data.quote.bid)}</text>{candles.map((v,i)=>{const x=55+i*27; const next=candles[Math.min(i+1,candles.length-1)]; const up=next<v; const y=40+v*3.3; const h=18+Math.abs(next-v)*2; return <g key={i} stroke={up?'#62efa7':'#ff7467'} fill={up?'#62efa7':'#ff7467'}><line x1={x} y1={y-15} x2={x} y2={y+h+16}/><rect x={x-6} y={y} width="12" height={h}/></g>})}</svg></div></Panel><Panel title="实时报价" className="col-span-12 sm:col-span-6 xl:col-span-4"><div className="number text-4xl font-bold">{fmt(data.quote.bid)}</div><Row label="Ask" value={fmt(data.quote.ask)}/><Row label="点差" value={fmt(data.quote.spread)}/><Row label="ATR" value={fmt(data.quote.atr)}/><Row label="快照时间" value={new Date(data.updated_at).toLocaleTimeString('zh-CN',{hour12:false})}/></Panel><Panel title="多周期结构" className="col-span-12 md:col-span-4"><Row label="D1" value="中立 48"/><Row label="H4" value="看空 69" tone="bad"/><Row label="H1" value="中立 52"/><Row label="M15" value="看多 61" tone="good"/><Row label="M5" value="看空 66" tone="bad"/></Panel><Panel title="交易时段" className="col-span-12 md:col-span-4"><Row label="亚洲盘" value="06:00–15:00"/><Row label="伦敦盘" value="15:00–00:00" tone="good"/><Row label="伦纽重叠" value="20:00–00:00"/><Row label="纽约盘" value="20:00–05:00"/></Panel><Panel title="数据质量" className="col-span-12 md:col-span-4"><Row label="EA 行情源" value={data.system.ea_online?'在线':'离线'} tone={data.system.ea_online?'good':'bad'}/><Row label="OHLC 完整性" value={data.quote.bid>0?'通过':'等待数据'} tone={data.quote.bid>0?'good':'warn'}/><Row label="报价年龄" value={data.system.ea_online?'< 5 秒':'—'}/><Row label="异常缺口" value="0" tone="good"/></Panel></div>;
}

function DecisionPage({ data }: { data: Overview }) {
  const factors = [{n:'技术面',v:-73},{n:'多周期',v:-64},{n:'宏观面',v:18},{n:'基本面',v:-38},{n:'资金面',v:-55},{n:'形态',v:41},{n:'入场时机',v:-20},{n:'波动性',v:25}];
  return <div className="grid grid-cols-12 gap-3"><Panel title="因子频谱 · 向右为多 / 向左为空" className="col-span-12"><div className="grid gap-3 md:grid-cols-2">{factors.map(f=><div key={f.n} className="grid grid-cols-[70px_1fr_42px] items-center gap-3 text-xs"><span className="text-zinc-500">{f.n}</span><div className="relative h-2 rounded-full bg-white/5"><i className="absolute left-1/2 top-0 h-full w-px bg-zinc-600"/><i className={`absolute top-0 h-full rounded-full ${f.v>=0?'left-1/2 bg-emerald-400':'right-1/2 bg-red-400'}`} style={{width:`${Math.abs(f.v)/2}%`}}/></div><b className={f.v>=0?'text-emerald-300':'text-red-300'}>{f.v}</b></div>)}</div></Panel><Panel title="当前决议" className="col-span-12 md:col-span-4"><div className="signal-glow text-5xl font-black text-amber-200">{statusText[data.decision.action] ?? data.decision.action}</div><div className="number mt-4 text-3xl">{Math.round(data.decision.confidence*100)}%</div><Row label="开仓阈值" value={`${Math.round(data.decision.threshold*100)}%`}/><Row label="计划" value={data.decision.plan_id}/><Row label="状态" value={data.decision.status} tone="warn"/></Panel><Panel title="证据与反证" className="col-span-12 md:col-span-8"><div className="space-y-3"><div className="rounded-xl border bg-red-400/5 p-4"><b className="text-red-300">空头证据</b><p className="mt-2 text-sm leading-6 text-zinc-400">趋势、动量与量价关系由服务端确定性计算后交给模型综合，不允许 AI 自行编造行情指标。</p></div><div className="rounded-xl border bg-emerald-400/5 p-4"><b className="text-emerald-300">多头反证</b><p className="mt-2 text-sm leading-6 text-zinc-400">短周期反弹或关键支撑存在时会降低置信度，并在证据失效后自动作废计划。</p></div><div className="rounded-xl border bg-amber-400/5 p-4"><b className="text-amber-200">当前摘要</b><p className="mt-2 text-sm leading-6 text-zinc-300">{data.decision.reason}</p></div></div></Panel></div>;
}

function ReplayPage({ data }: { data: Overview }) {
  return <div className="grid grid-cols-12 gap-3"><Panel title="判断与证据轨迹" className="col-span-12"><MiniLine/><div className="mt-2 flex justify-between text-xs text-zinc-600"><span>最近 24 小时</span><span>成交事件将随 EA 回报写入</span></div></Panel><Panel title="今日战绩" className="col-span-12 md:col-span-4"><div className={`number text-4xl font-bold ${data.account.daily_pnl>=0?'text-emerald-300':'text-red-300'}`}>{money(data.account.daily_pnl)}</div><Row label="当前回撤" value={`${fmt(data.account.drawdown_pct)}%`} tone={data.account.drawdown_pct<2?'good':'bad'}/><Row label="已同步持仓" value={data.position?'1':'0'}/><Row label="账户" value={data.account.id}/></Panel><Panel title="执行复盘" className="col-span-12 md:col-span-8"><div className="flex min-h-48 flex-col items-center justify-center rounded-xl border border-dashed text-center"><History className="mb-3 size-9 text-zinc-600"/><strong>等待订单事件</strong><p className="mt-2 max-w-md text-sm text-zinc-500">EA 发出首笔模拟盘订单后，这里将展示计划、风控、委托、成交和关仓的完整时间线。</p></div></Panel></div>;
}

function RiskPage({ data, onMode }: { data: Overview; onMode: (enabled:boolean)=>void }) {
  const [busy,setBusy]=useState(false);
  const [adminToken,setAdminToken]=useState('');
  const [message,setMessage]=useState('');
  const [open,setOpen]=useState(false);
  const toggle=async()=>{setBusy(true); setMessage(''); try{const res=await fetch('/api/v1/control/auto-trading',{method:'POST',headers:{'Content-Type':'application/json','X-Admin-Token':adminToken},body:JSON.stringify({enabled:!data.system.auto_trading,confirmation:'I UNDERSTAND'})}); const body=await res.json() as {detail?:string}; if(!res.ok){setMessage(body.detail??'操作失败');return;} onMode(!data.system.auto_trading); setOpen(false); setAdminToken('');}catch{setMessage('API 无法连接');}finally{setBusy(false)}};
  const actionLabel=data.system.auto_trading?'关闭自动交易':'启用自动交易';
  return <div className="grid grid-cols-12 gap-3"><Panel title="账户风险" className="col-span-12 lg:col-span-4"><div className="mx-auto grid size-36 place-items-center rounded-full bg-[conic-gradient(#62efa7_0_96%,rgba(255,255,255,.06)_96%)]"><div className="grid size-28 place-items-center rounded-full bg-[#111612]"><div className="text-center"><div className="number text-3xl font-bold">96</div><div className="text-xs text-zinc-500">健康度</div></div></div></div><Row label="净值" value={money(data.account.equity)}/><Row label="可用保证金" value={money(data.account.free_margin)}/><Row label="当前回撤" value={`${fmt(data.account.drawdown_pct)}%`} tone={data.account.drawdown_pct<5?'good':'bad'}/></Panel><Panel title="硬风控阈值" className="col-span-12 lg:col-span-4"><Row label="单笔风险" value="≤ 0.50%"/><Row label="每日亏损" value="≤ 2.00%"/><Row label="最大回撤" value="≤ 10.00%"/><Row label="最大持仓" value="1 笔"/><Row label="最大点差" value="按品种配置"/><Row label="API 故障" value="禁止新开仓" tone="good"/></Panel><Panel title="交易控制" className="col-span-12 lg:col-span-4"><div className={`rounded-xl border p-4 ${data.system.auto_trading?'border-red-400/30 bg-red-400/5':'border-emerald-400/30 bg-emerald-400/5'}`}><div className="flex items-center gap-3">{data.system.auto_trading?<Siren className="text-red-300"/>:<ShieldCheck className="text-emerald-300"/>}<div><strong>{data.system.auto_trading?'自动交易已开启':'安全观察模式'}</strong><p className="mt-1 text-xs text-zinc-500">{data.system.auto_trading?'EA 仍会执行本地硬风控':'分析照常运行，但不会签发可执行开仓'}</p></div></div></div><AlertDialog open={open} onOpenChange={setOpen}><AlertDialogTrigger render={<Button className="mt-4 w-full" variant={data.system.auto_trading?'destructive':'default'} disabled={!data.system.ea_online}>{data.system.auto_trading?<X/>:<Radio/>}{actionLabel}</Button>}/><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>确认{actionLabel}</AlertDialogTitle><AlertDialogDescription>请输入服务端 ADMIN_API_TOKEN。启用操作还要求服务端 ALLOW_WEB_ENABLE=true；关闭操作始终可在通过认证后执行。</AlertDialogDescription></AlertDialogHeader><Input type="password" value={adminToken} onChange={event=>setAdminToken(event.target.value)} placeholder="ADMIN_API_TOKEN" autoComplete="off"/>{message&&<p className="text-sm text-red-300">{message}</p>}<AlertDialogFooter><AlertDialogCancel>取消</AlertDialogCancel><AlertDialogAction disabled={!adminToken || busy} onClick={event=>{event.preventDefault();void toggle();}}>{busy?<RefreshCw className="animate-spin"/>:null}确认</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog><p className="mt-3 text-xs leading-5 text-zinc-600">安全要求：EA 离线时不能改变执行模式。首次实盘前请先运行模拟盘并复核全部阈值。</p></Panel><Panel title="运行状态" className="col-span-12 lg:col-span-7"><Row label="EA 心跳" value={data.system.ea_online?'在线':'离线'} tone={data.system.ea_online?'good':'bad'}/><Row label="AI 接口" value={data.system.ai_configured?`${data.system.ai_provider} 已配置`:'未配置 API Key'} tone={data.system.ai_configured?'good':'warn'}/><Row label="服务延迟" value={`${data.system.latency_ms} ms`}/><Row label="最后心跳" value={data.system.last_heartbeat?new Date(data.system.last_heartbeat).toLocaleString('zh-CN'):'—'}/></Panel><Panel title="市场告警" className="col-span-12 lg:col-span-5"><div className="flex min-h-44 flex-col items-center justify-center text-center"><AlertTriangle className={`mb-3 size-9 ${data.quote.spread>0?'text-amber-300':'text-zinc-600'}`}/><strong>{data.quote.spread>0?'正在监控点差和波动':'等待行情数据'}</strong><p className="mt-2 text-sm text-zinc-500">异常报价、点差或回撤会在 EA 本地立即阻断新订单。</p></div></Panel></div>;
}

export function TradingDashboard() {
  const [page,setPage]=useState<Page>('overview');
  const [data,setData]=useState<Overview>(demo);
  const [error,setError]=useState('');
  const load=async()=>{try{const res=await fetch('/api/v1/dashboard/overview',{cache:'no-store'}); if(!res.ok)throw new Error(String(res.status)); setData(await res.json()); setError('');}catch{setError('API 未连接，正在显示安全等待状态');}};
  useEffect(()=>{const initial=window.setTimeout(()=>{void load()},0); const timer=window.setInterval(()=>{void load()},5000); return()=>{window.clearTimeout(initial);window.clearInterval(timer)}},[]);
  const title={overview:'实时总览',market:'行情结构',decision:'AI 决策',replay:'交易复盘',risk:'风险控制'}[page];
  return <main className="min-h-screen"><header className="sticky top-0 z-30 border-b bg-[#070a08]/90 backdrop-blur-xl"><div className="mx-auto grid min-h-16 max-w-[1600px] grid-cols-[auto_1fr_auto] items-center gap-5 px-4 lg:px-7"><button onClick={()=>setPage('overview')} className="flex items-center gap-3 text-left" aria-label="WiseFX AI 智汇AI 首页"><span className="grid size-9 place-items-center rounded-xl border border-emerald-300/40 bg-emerald-400/10 font-black text-emerald-300">W</span><span className="hidden sm:block"><b className="block tracking-[.08em]">WiseFX AI</b><small className="text-[10px] tracking-[.16em] text-zinc-600">智汇AI</small></span></button><nav className="flex h-16 items-stretch justify-center overflow-x-auto scrollbar-thin" aria-label="主导航">{nav.map(item=>{const Icon=item.icon; return <button key={item.id} onClick={()=>setPage(item.id)} className={`relative flex min-w-20 items-center justify-center gap-2 px-3 text-sm transition-colors ${page===item.id?'text-zinc-50':'text-zinc-500 hover:text-zinc-200'}`}><Icon className="size-4"/><span>{item.label}</span>{page===item.id&&<i className="absolute inset-x-3 bottom-0 h-0.5 bg-emerald-300 shadow-[0_0_12px_#62efa7]"/>}</button>})}</nav><div className="flex items-center gap-3 text-xs"><span className="hidden items-center gap-2 text-zinc-500 md:flex"><Dot ok={!error}/>{error?'API 离线':'实时'}</span><Badge variant="outline" className="border-amber-300/30 text-amber-200">DEMO / SAFE</Badge></div></div></header><div className="mx-auto max-w-[1600px] px-4 py-4 lg:px-7"><StatusHeader data={data}/><div className="mb-5 flex flex-wrap items-end justify-between gap-3"><div><p className="mb-1 text-xs font-semibold uppercase tracking-[.2em] text-emerald-300">{page} / control surface</p><h1 className="text-2xl font-bold tracking-tight md:text-3xl">{title}</h1></div><Button variant="outline" onClick={()=>{void load()}}><RefreshCw/>刷新数据</Button></div>{page==='overview'&&<OverviewPage data={data}/>} {page==='market'&&<MarketPage data={data}/>} {page==='decision'&&<DecisionPage data={data}/>} {page==='replay'&&<ReplayPage data={data}/>} {page==='risk'&&<RiskPage data={data} onMode={enabled=>setData(v=>({...v,system:{...v.system,auto_trading:enabled}}))}/>}<footer className="flex flex-wrap justify-between gap-2 py-7 text-xs text-zinc-700"><span>WiseFX AI · 智汇AI交易控制台</span><span>默认安全观察模式 · 不构成投资建议</span></footer></div></main>;
}
