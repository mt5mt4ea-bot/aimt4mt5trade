//+------------------------------------------------------------------+
//|                                                GenesisAI_EA.mq5  |
//|  AI analysis client with local hard-risk controls (MT5)          |
//+------------------------------------------------------------------+
#property copyright "Genesis AI"
#property version   "1.000"
#property strict
#property description "Add https://ai.mt4mt5.trade to Tools > Options > Expert Advisors > Allow WebRequest."
#property description "AUTO and live trading are disabled by default. Test on a demo account first."

#include <Trade/Trade.mqh>

input group "API Connection"
input string InpApiBaseUrl              = "https://ai.mt4mt5.trade";
input string InpEaApiKey                = "PASTE_SERVER_EA_API_KEY_HERE";
input int    InpAnalysisIntervalSeconds = 300;
input int    InpHeartbeatSeconds        = 30;
input int    InpHttpTimeoutMs           = 8000;

input group "Execution Safety"
input bool   InpAllowAutoTrading        = false;
input bool   InpAllowLiveAccount        = false;
input double InpMinConfidence           = 0.65;
input ulong  InpMagicNumber             = 26091301;
input double InpRiskPercent             = 0.50;
input double InpMaxVolume               = 1.00;
input int    InpMaxPositions            = 1;
input int    InpMaxSpreadPoints         = 50;
input int    InpMaxSlippagePoints       = 30;
input int    InpMaxEntryDeviationPoints = 100;
input double InpMaxDailyLossPercent     = 2.0;
input double InpMaxDrawdownPercent      = 10.0;

CTrade trade;
datetime g_lastHeartbeat = 0;
datetime g_lastAnalysis = 0;
double g_sessionStartEquity = 0;
double g_peakEquity = 0;
string g_lastPlanId = "";
bool g_serverAutoTrading = false;

string IsoUtc()
  {
   string value=TimeToString(TimeGMT(),TIME_DATE|TIME_SECONDS);
   StringReplace(value,".","-");
   StringReplace(value," ","T");
   return value+"Z";
  }

string JsonEscape(string value)
  {
   StringReplace(value,"\\","\\\\");
   StringReplace(value,"\"","\\\"");
   StringReplace(value,"\r","\\r");
   StringReplace(value,"\n","\\n");
   return value;
  }

string JsonString(const string json,const string key,const string fallback="")
  {
   int p=StringFind(json,"\""+key+"\"");
   if(p<0) return fallback;
   p=StringFind(json,":",p);
   if(p<0) return fallback;
   p++;
   while(p<StringLen(json) && StringGetCharacter(json,p)<=32) p++;
   if(StringGetCharacter(json,p)!=34) return fallback;
   p++;
   int e=p;
   while(e<StringLen(json))
     {
      if(StringGetCharacter(json,e)==34 && (e==p || StringGetCharacter(json,e-1)!=92))
         return StringSubstr(json,p,e-p);
      e++;
     }
   return fallback;
  }

double JsonNumber(const string json,const string key,const double fallback=0.0)
  {
   int p=StringFind(json,"\""+key+"\"");
   if(p<0) return fallback;
   p=StringFind(json,":",p);
   if(p<0) return fallback;
   p++;
   while(p<StringLen(json) && StringGetCharacter(json,p)<=32) p++;
   int e=p;
   while(e<StringLen(json))
     {
      ushort c=StringGetCharacter(json,e);
      if(c==44 || c==125 || c==93 || c<=32) break;
      e++;
     }
   string value=StringSubstr(json,p,e-p);
   if(StringLen(value)==0) return fallback;
   return StringToDouble(value);
  }

bool JsonBool(const string json,const string key,const bool fallback=false)
  {
   int p=StringFind(json,"\""+key+"\"");
   if(p<0) return fallback;
   p=StringFind(json,":",p);
   if(p<0) return fallback;
   p++;
   while(p<StringLen(json) && StringGetCharacter(json,p)<=32) p++;
   if(StringSubstr(json,p,4)=="true") return true;
   if(StringSubstr(json,p,5)=="false") return false;
   return fallback;
  }

uint PlanHash(const string value)
  {
   uint hash=2166136261;
   for(int i=0;i<StringLen(value);i++)
     {
      hash^=(uint)StringGetCharacter(value,i);
      hash*=16777619;
     }
   return hash;
  }

bool HttpRequest(const string method,const string path,const string body,string &response,int &status)
  {
   if(MQLInfoInteger(MQL_TESTER))
     {
      Print("Genesis AI: WebRequest is unavailable in Strategy Tester; use recorded plans for backtests.");
      return false;
     }
   if(InpEaApiKey=="" || InpEaApiKey=="PASTE_SERVER_EA_API_KEY_HERE")
     {
      Print("Genesis AI: set InpEaApiKey before connecting.");
      return false;
     }
   string url=InpApiBaseUrl+path;
   string headers="Content-Type: application/json\r\nAccept: application/json\r\nX-EA-Key: "+InpEaApiKey+"\r\n";
   char data[];
   char result[];
   string resultHeaders;
   int copied=StringToCharArray(body,data,0,WHOLE_ARRAY,CP_UTF8);
   if(copied>0) ArrayResize(data,copied-1);
   ResetLastError();
   status=WebRequest(method,url,headers,InpHttpTimeoutMs,data,result,resultHeaders);
   if(status<0)
     {
      PrintFormat("Genesis AI: WebRequest failed, error=%d, url=%s",GetLastError(),url);
      return false;
     }
   response=CharArrayToString(result,0,WHOLE_ARRAY,CP_UTF8);
   if(status<200 || status>=300)
     {
      PrintFormat("Genesis AI: HTTP %d: %s",status,response);
      return false;
     }
   return true;
  }

double IndicatorValue(const int handle,const int buffer=0)
  {
   if(handle==INVALID_HANDLE) return 0;
   double values[];
   ArraySetAsSeries(values,true);
   double result=0;
   if(CopyBuffer(handle,buffer,0,1,values)==1) result=values[0];
   IndicatorRelease(handle);
   return result;
  }

int CountManagedPositions()
  {
   int count=0;
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)==_Symbol && (ulong)PositionGetInteger(POSITION_MAGIC)==InpMagicNumber) count++;
     }
   return count;
  }

string PositionJson()
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagicNumber) continue;
      ENUM_POSITION_TYPE type=(ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      return StringFormat("{\"side\":\"%s\",\"volume\":%.2f,\"open_price\":%s,\"stop_loss\":%s,\"take_profit\":%s,\"pnl\":%.2f,\"ticket\":%I64u}",
                          type==POSITION_TYPE_BUY?"LONG":"SHORT",PositionGetDouble(POSITION_VOLUME),
                          DoubleToString(PositionGetDouble(POSITION_PRICE_OPEN),_Digits),DoubleToString(PositionGetDouble(POSITION_SL),_Digits),
                          DoubleToString(PositionGetDouble(POSITION_TP),_Digits),PositionGetDouble(POSITION_PROFIT),ticket);
     }
   return "null";
  }

string AccountId()
  {
   return IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
  }

void SendHeartbeat()
  {
   string body=StringFormat("{\"ea_instance_id\":\"mt5-%s-%s\",\"account_id\":\"%s\",\"symbol\":\"%s\",\"ea_version\":\"0.10\",\"auto_trading_local\":%s,\"timestamp\":\"%s\"}",
                            AccountId(),_Symbol,AccountId(),_Symbol,InpAllowAutoTrading?"true":"false",IsoUtc());
   string response;
   int status=0;
   if(HttpRequest("POST","/api/v1/ea/heartbeat",body,response,status))
      g_serverAutoTrading=JsonBool(response,"auto_trading_enabled",false);
  }

string CreateSnapshotJson()
  {
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) return "";
   double atr=IndicatorValue(iATR(_Symbol,PERIOD_M15,14));
   double rsi=IndicatorValue(iRSI(_Symbol,PERIOD_M15,14,PRICE_CLOSE));
   double ema20=IndicatorValue(iMA(_Symbol,PERIOD_M15,20,0,MODE_EMA,PRICE_CLOSE));
   double h1ema20=IndicatorValue(iMA(_Symbol,PERIOD_H1,20,0,MODE_EMA,PRICE_CLOSE));
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity>g_peakEquity) g_peakEquity=equity;
   double drawdown=(g_peakEquity>0)?MathMax(0,(g_peakEquity-equity)/g_peakEquity*100.0):0;
   double dailyPnl=equity-g_sessionStartEquity;
   string requestId=StringFormat("mt5-%s-%I64d-%I64d",AccountId(),(long)TimeGMT(),(long)GetTickCount64());
   return StringFormat("{\"request_id\":\"%s\",\"ea_instance_id\":\"mt5-%s-%s\",\"timestamp\":\"%s\",\"account\":{\"account_id\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"free_margin\":%.2f,\"daily_pnl\":%.2f,\"drawdown_pct\":%.4f,\"is_demo\":%s},\"quote\":{\"symbol\":\"%s\",\"bid\":%s,\"ask\":%s,\"spread\":%s,\"atr\":%s},\"indicators\":{\"m15_rsi\":%.4f,\"m15_ema20\":%s,\"h1_ema20\":%s},\"position\":%s,\"strategy_version\":\"genesis-mt5-0.1.0\"}",
                       requestId,AccountId(),_Symbol,IsoUtc(),AccountId(),AccountInfoDouble(ACCOUNT_BALANCE),equity,AccountInfoDouble(ACCOUNT_MARGIN_FREE),dailyPnl,drawdown,
                       AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_DEMO?"true":"false",_Symbol,DoubleToString(tick.bid,_Digits),DoubleToString(tick.ask,_Digits),
                       DoubleToString(tick.ask-tick.bid,_Digits),DoubleToString(atr,_Digits),rsi,DoubleToString(ema20,_Digits),DoubleToString(h1ema20,_Digits),PositionJson());
  }

double NormalizeVolume(double volume)
  {
   double minVolume=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MIN);
   double maxVolume=MathMin(InpMaxVolume,SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_MAX));
   double step=SymbolInfoDouble(_Symbol,SYMBOL_VOLUME_STEP);
   if(step<=0) return 0;
   volume=MathFloor(volume/step)*step;
   volume=MathMax(minVolume,MathMin(maxVolume,volume));
   return NormalizeDouble(volume,2);
  }

bool LocalRiskCheck(const string action,const double confidence,const double entry,const double sl,const double tp,string &reason)
  {
   if(!InpAllowAutoTrading) { reason="LOCAL_AUTO_DISABLED"; return false; }
   if(!g_serverAutoTrading) { reason="SERVER_AUTO_DISABLED"; return false; }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) { reason="TERMINAL_TRADE_DISABLED"; return false; }
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL && !InpAllowLiveAccount) { reason="LIVE_ACCOUNT_DISABLED"; return false; }
   if(confidence<InpMinConfidence) { reason="CONFIDENCE_BELOW_THRESHOLD"; return false; }
   if(CountManagedPositions()>=InpMaxPositions && (action=="LONG" || action=="SHORT")) { reason="MAX_POSITIONS"; return false; }
   MqlTick tick;
   if(!SymbolInfoTick(_Symbol,tick)) { reason="NO_QUOTE"; return false; }
   if((tick.ask-tick.bid)/_Point>InpMaxSpreadPoints) { reason="SPREAD_LIMIT"; return false; }
   double currentEquity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(g_sessionStartEquity>0 && (g_sessionStartEquity-currentEquity)/g_sessionStartEquity*100.0>=InpMaxDailyLossPercent) { reason="DAILY_LOSS_LIMIT"; return false; }
   if(g_peakEquity>0 && (g_peakEquity-currentEquity)/g_peakEquity*100.0>=InpMaxDrawdownPercent) { reason="DRAWDOWN_LIMIT"; return false; }
   double mid=(tick.ask+tick.bid)/2.0;
   if((action=="LONG" || action=="SHORT") && MathAbs(mid-entry)/_Point>InpMaxEntryDeviationPoints) { reason="ENTRY_DEVIATION"; return false; }
   if(action=="LONG" && !(sl<mid && tp>mid)) { reason="INVALID_LONG_LEVELS"; return false; }
   if(action=="SHORT" && !(sl>mid && tp<mid)) { reason="INVALID_SHORT_LEVELS"; return false; }
   int stopLevel=(int)SymbolInfoInteger(_Symbol,SYMBOL_TRADE_STOPS_LEVEL);
   if((action=="LONG" || action=="SHORT") && (MathAbs(mid-sl)/_Point<stopLevel || MathAbs(tp-mid)/_Point<stopLevel)) { reason="BROKER_STOP_LEVEL"; return false; }
   reason="OK";
   return true;
  }

double CalculateVolume(const double entry,const double sl)
  {
   double tickSize=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_SIZE);
   double tickValue=SymbolInfoDouble(_Symbol,SYMBOL_TRADE_TICK_VALUE);
   double riskAmount=AccountInfoDouble(ACCOUNT_EQUITY)*InpRiskPercent/100.0;
   if(tickSize<=0 || tickValue<=0 || riskAmount<=0 || MathAbs(entry-sl)<=0) return 0;
   double lossPerLot=(MathAbs(entry-sl)/tickSize)*tickValue;
   return NormalizeVolume(riskAmount/lossPerLot);
  }

void ReportEvent(const string planId,const string eventType,const ulong ticket,const string message)
  {
   string eventId=StringFormat("evt-%s-%I64d-%I64d",AccountId(),(long)TimeGMT(),(long)GetTickCount64());
   string body=StringFormat("{\"event_id\":\"%s\",\"plan_id\":\"%s\",\"account_id\":\"%s\",\"event_type\":\"%s\",\"ticket\":%I64u,\"message\":\"%s\",\"timestamp\":\"%s\"}",eventId,JsonEscape(planId),AccountId(),eventType,ticket,JsonEscape(message),IsoUtc());
   string response;
   int status=0;
   HttpRequest("POST","/api/v1/order-events",body,response,status);
  }

void CloseManagedPositions(const string planId)
  {
   for(int i=PositionsTotal()-1;i>=0;i--)
     {
      ulong ticket=PositionGetTicket(i);
      if(ticket==0 || !PositionSelectByTicket(ticket)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=_Symbol || (ulong)PositionGetInteger(POSITION_MAGIC)!=InpMagicNumber) continue;
      bool ok=trade.PositionClose(ticket,InpMaxSlippagePoints);
      ReportEvent(planId,ok?"POSITION_CLOSED":"ORDER_FAILED",ticket,ok?"close accepted":trade.ResultRetcodeDescription());
     }
  }

void HandlePlan(const string response)
  {
   string planId=JsonString(response,"plan_id","");
   string planKey="GenesisAI.LastPlan."+AccountId()+"."+_Symbol;
   uint planHash=PlanHash(planId);
   if(planId=="" || planId==g_lastPlanId || (GlobalVariableCheck(planKey) && (uint)GlobalVariableGet(planKey)==planHash)) return;
   string action=JsonString(response,"action","HOLD");
   string status=JsonString(response,"status","OBSERVE");
   double confidence=JsonNumber(response,"confidence",0);
   double entry=JsonNumber(response,"entry_price",0);
   double sl=JsonNumber(response,"stop_loss",0);
   double tp=JsonNumber(response,"take_profit",0);
   int expires=(int)JsonNumber(response,"expires_in_seconds",0);
   g_serverAutoTrading=JsonBool(response,"auto_trading_enabled",false);
   g_lastPlanId=planId;
   GlobalVariableSet(planKey,(double)planHash);
   if(status!="ACTIONABLE" || expires<=0 || action=="HOLD")
     {
      PrintFormat("Genesis AI: plan %s observed only, action=%s status=%s",planId,action,status);
      return;
     }
   string rejectReason;
   if(!LocalRiskCheck(action,confidence,entry,sl,tp,rejectReason))
     {
      PrintFormat("Genesis AI: plan %s rejected locally: %s",planId,rejectReason);
      ReportEvent(planId,"PLAN_REJECTED",0,rejectReason);
      return;
     }
   if(action=="CLOSE") { CloseManagedPositions(planId); return; }
   if(action!="LONG" && action!="SHORT") return;
   double volume=CalculateVolume(entry,sl);
   if(volume<=0) { ReportEvent(planId,"PLAN_REJECTED",0,"INVALID_VOLUME"); return; }
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpMaxSlippagePoints);
   bool ok=(action=="LONG")?trade.Buy(volume,_Symbol,0,sl,tp,"GenesisAI:"+planId):trade.Sell(volume,_Symbol,0,sl,tp,"GenesisAI:"+planId);
   ReportEvent(planId,ok?"ORDER_SUBMITTED":"ORDER_FAILED",trade.ResultOrder(),ok?trade.ResultRetcodeDescription():trade.ResultRetcodeDescription());
  }

void AnalyzeNow()
  {
   string body=CreateSnapshotJson();
   if(body=="") return;
   string response;
   int status=0;
   if(HttpRequest("POST","/api/v1/market/snapshot",body,response,status)) HandlePlan(response);
  }

int OnInit()
  {
   if(InpAnalysisIntervalSeconds<30 || InpHeartbeatSeconds<10)
     {
      Print("Genesis AI: intervals are too short.");
      return INIT_PARAMETERS_INCORRECT;
     }
   g_sessionStartEquity=AccountInfoDouble(ACCOUNT_EQUITY);
   g_peakEquity=g_sessionStartEquity;
   trade.SetExpertMagicNumber(InpMagicNumber);
   EventSetTimer(1);
   Print("Genesis AI initialized in ",InpAllowAutoTrading?"AUTO-REQUESTED":"OBSERVE"," mode. Add WebRequest URL: ",InpApiBaseUrl);
   if(AccountInfoInteger(ACCOUNT_TRADE_MODE)==ACCOUNT_TRADE_MODE_REAL && !InpAllowLiveAccount)
      Print("Genesis AI safety: live-account execution is disabled.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
  }

void OnTimer()
  {
   datetime now=TimeCurrent();
   if(now-g_lastHeartbeat>=InpHeartbeatSeconds)
     {
      g_lastHeartbeat=now;
      SendHeartbeat();
     }
   if(now-g_lastAnalysis>=InpAnalysisIntervalSeconds)
     {
      g_lastAnalysis=now;
      AnalyzeNow();
     }
  }

void OnTick()
  {
   double equity=AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity>g_peakEquity) g_peakEquity=equity;
   // OnTick remains intentionally lightweight. Broker-side SL/TP is always set on entry.
  }

void OnTradeTransaction(const MqlTradeTransaction &trans,const MqlTradeRequest &request,const MqlTradeResult &result)
  {
   // Keep this handler short because transaction order is not guaranteed and the terminal queue is finite.
   if(trans.type==TRADE_TRANSACTION_DEAL_ADD && trans.deal>0)
      PrintFormat("Genesis AI: deal event %I64u, order %I64u",trans.deal,trans.order);
  }
