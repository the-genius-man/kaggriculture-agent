"""V12 plus surgical patches. Stdlib only. Does not replace agents/main_v12.py.

Patches from live top-farm games + engine rules:
- Never issue more PLANT orders than remaining seeds (atomic crop drop).
- Reserve a seed when walking to PLANT.
- Wheat-fill empty tiles after harvest / expansion (wheat glut curve is log).
- After day 14, rotate toward tomato/carrot like current #1/#2 games.
- Keep 3 market slots for buys so seed restock is not truncated by sells.
- Yield-aware melon harvest (engine max_yield_day is 12).
"""
import copy

CFG = {}  # replaced by the trainer
CROPS={'WHEAT':(10,2,4,4),'CARROT':(20,2,3,3),'MELON':(80,10,12,6),'TOMATO':(50,8,11,4),'STRAWBERRY':(100,10,16,4)}
ANIMALS={'COW':(400,'MILK',8,2),'SHEEP':(500,'WOOL',6,3),'GOOSE':(300,'EGG',4,1)}
BASE={'WHEAT':25,'CARROT':35,'MELON':250,'TOMATO':60,'STRAWBERRY':120,'MILK':160,'WOOL':200,'EGG':50,'FERTILIZER':100}

def agent(obs):
    me=copy.deepcopy(obs['farms'][obs['player']]);pr=copy.deepcopy(obs['private'])
    tiles=me['tiles'];n=len(tiles);day=obs['day'];hour=obs['hour'];prices=obs['market']['prices'];remaining=30-day
    shed=pr['shed'];seeds=pr['seeds'];invs=pr['inventories'];positions=[me['farmer']]+me['hands']
    center=n//2;access=[(center-1,center-1),(center,center-1),(center-1,center),(center,center)]
    def dist(a,b):return abs(a[0]-b[0])+abs(a[1]-b[1])
    def move(a,b):
        dx,dy=b[0]-a[0],b[1]-a[1]
        return ['EAST' if dx>0 else 'WEST'] if abs(dx)>=abs(dy) and dx else ['SOUTH' if dy>0 else 'NORTH']
    coords=[(x,y) for y in range(n) for x in range(n) if tiles[y][x]!='LOCKED']
    animals=[(x,y) for x,y in coords if isinstance(tiles[y][x],dict) and tiles[y][x].get('animal')]
    counts={c:sum(isinstance(tiles[y][x],dict) and tiles[y][x].get('crop')==c for x,y in coords) for c in CROPS}
    nlive=len(animals);claimed=set();actions=[]
    other=obs['farms'][1-obs['player']]
    opponent_crops={c:sum(isinstance(t,dict) and t.get('crop')==c for row in other['tiles'] for t in row) for c in CROPS}
    occupied=sum(isinstance(tiles[y][x],dict) and bool(tiles[y][x].get('crop') or tiles[y][x].get('animal')) for x,y in coords)
    empty_n=sum(1 for x,y in coords if tiles[y][x] is None)
    underfilled=empty_n>CFG.get('empty_ok',2)

    def crop_value(c):
        cost,first,peak,yld=CROPS[c]
        if day+first>=29 or (hour>=21 and c!='WHEAT'):return -1
        lifespan=min(peak,remaining-2)
        if c in ('TOMATO','STRAWBERRY'):
            interval=1 if c=='TOMATO' else 2;yld=max(0,min(4,1+(remaining-2-first)//interval))
        price=prices[c]
        if CFG['opponent_weight']>0:price=max(BASE[c]*.15,price-CFG['opponent_weight']*opponent_crops[c]*BASE[c]*.06)
        if c in ('MELON','STRAWBERRY'):price=max(BASE[c]*.20,price-counts[c]*(18 if c=='MELON' else 12))
        if c=='WHEAT' and nlive:price=max(price,32)
        if day>=CFG.get('late_rotate',14):
            if c=='TOMATO':price=max(price,BASE[c]*1.15)
            if c=='CARROT':price=max(price,42)
            if c=='STRAWBERRY':price=max(BASE[c]*.15,price-counts[c]*18)
        if underfilled and c=='WHEAT' and CFG.get('bulk_wheat'):price=max(price,50)
        if underfilled and c=='STRAWBERRY' and day<=18:price=max(price,BASE[c]*1.2)
        return (yld*price-cost)/(lifespan+4)*CFG['crop_bias']
    crop_scores={c:crop_value(c) for c in CROPS}
    for idx,pos0 in enumerate(positions):
        pos=tuple(pos0);inv=invs[idx];best=(-1,None,None);carried=next((a for a in ANIMALS if inv.get(a,0)),None)
        nearest_shed=min(access,key=lambda q:dist(pos,q));ds=dist(pos,nearest_shed)
        def offer(value,target,act,key=None):
            nonlocal best
            if key is not None and key in claimed:return
            distance=dist(pos,target)
            if day==29 and CFG['liquidate']:
                if act[0] not in ('HARVEST','COLLECT_FERTILIZER','DROP'):return
                delivery=0 if act[0]=='DROP' else min(dist(target,s) for s in access)+1
                if distance+1+delivery>23-hour:return
            if distance>23-hour:return
            score=value/(1+distance*.85)
            if score>best[0]:best=(score,target,(act,key))
        goods=sum(v for k,v in inv.items() if k not in ('WHEAT','FERTILIZER') and k not in ANIMALS)
        goods_value=sum(v*prices.get(k,0) for k,v in inv.items() if k not in ANIMALS and k!='WHEAT')
        deposit=(day==29 and hour+ds>=19 and sum(inv.values())>0) or goods>=CFG['drop_units'] or inv.get('FERTILIZER',0)>=4
        deposit=deposit or goods_value>=CFG['drop_value'] or (CFG['cash_release'] and me['money']<100 and goods_value>0)
        if day==29 and CFG['liquidate'] and sum(inv.values())>0:deposit=True
        if deposit and not carried:
            urgency=3000 if day==29 and hour+ds>=20 else max(90,goods_value*CFG['deposit_bias'])
            offer(urgency,nearest_shed,['DROP'])
        if carried:
            kind='COOP' if carried=='GOOSE' else 'PASTURE'
            for x,y in coords:
                t=tiles[y][x]
                if t is None:offer(280-5*min(dist((x,y),s) for s in access),(x,y),['BUILD_COOP' if kind=='COOP' else 'BUILD_PASTURE'],('tile',x,y))
                elif isinstance(t,dict) and t.get('kind')==kind and not t.get('animal'):offer(600,(x,y),['PLACE',carried,1],('tile',x,y))
        else:
            pending=next((a for a in ANIMALS if shed.get(a,0)>0),None)
            if pending and day<20:offer(350,nearest_shed,['PICKUP',pending,1])
        if nlive and inv.get('WHEAT',0)==0 and shed.get('WHEAT',0)>0 and hour<22 and (not CFG['feed_fix'] or (day<29 and any(not tiles[y][x].get('fed_today') for x,y in animals))):
            offer(210,nearest_shed,['PICKUP','WHEAT',min(4,shed['WHEAT'])])
        for x,y in coords:
            t=tiles[y][x];target=(x,y);key=('tile',x,y)
            if key in claimed:continue
            if isinstance(t,dict) and t.get('animal'):
                species=t['animal'];cost,product,first,interval=ANIMALS[species];price=prices[product]
                if not t.get('fed_today') and inv.get('WHEAT',0):offer(190+130*t.get('consecutive_unfed',0)+hour*3,target,['FEED'],key)
                if t.get('yield_units',0):offer(60+t['yield_units']*max(price,10)*.8,target,['HARVEST'],key)
                if not t.get('cared_today') and day<29 and t.get('yield_units',0)<5:
                    care_v=max(12,min(price,BASE[product]*CFG['care_cap']))*CFG['care_bias']
                    if underfilled:care_v*=CFG.get('care_when_filling',1.0)
                    offer(care_v,target,['CARE'],key)
                if t.get('fertilizer_available'):offer(max(40,prices['FERTILIZER'])*.85,target,['COLLECT_FERTILIZER'],key)
            elif isinstance(t,dict) and t.get('kind')=='PLANT':
                c=t['crop'];cost,first,peak,yld=CROPS[c];age=day-t['planted_day'];yield_units=t.get('yield_units',0)
                fertile=t.get('fertilized_until_day',-1)>=day
                needs_fert=(c in ('TOMATO','STRAWBERRY') and age>=first-2) or (c not in ('TOMATO','STRAWBERRY') and age>=max(0,first-1) and age<peak)
                if not fertile and needs_fert and inv.get('FERTILIZER',0) and day<29:
                    offer(min(200,prices[c]*1.4)*CFG['fert_bias'],target,['FERTILIZE'],key)
                ready=yield_units>0 and age>=first and (c in ('TOMATO','STRAWBERRY') or age>=peak or yield_units>=6 or day==29)
                if ready:offer(100+yield_units*prices[c]*.55+(200 if day==29 else 0),target,['HARVEST'],key)
                drought=t.get('consecutive_unwatered',0)
                if not t.get('watered_today') and not (day==29 and ready):
                    if (not underfilled) or drought>=1 or hour>=CFG.get('water_relax_hour',18):
                        offer(95+hour*4+120*drought,target,['WATER'],key)
            elif t is None and not carried and hour<22:
                available=[c for c in CROPS if seeds.get(c,0)>0 and crop_scores[c]>0]
                if available:
                    c=max(available,key=lambda c:crop_scores[c])
                    plant_score=max(CFG['plant_floor'],crop_scores[c])
                    if underfilled:plant_score+=CFG.get('fill_push',80)
                    offer(plant_score,target,['PLANT',c],key)
            elif isinstance(t,dict) and t.get('kind')=='WEED' and day<26:offer(20,target,['DIG'],key)
        if best[1] is None:action=['PASS']
        else:
            _,target,(task,key)=best
            if key:claimed.add(key)
            if pos!=target:
                action=move(pos,target)
                if task[0]=='PLANT' and len(task)>1 and seeds.get(task[1],0)>0:
                    seeds[task[1]]-=1
            else:
                action=task;op=action[0];x,y=pos;t=tiles[y][x]
                if op=='PLANT':
                    crop=action[1]
                    if seeds.get(crop,0)<=0:
                        alt=[c for c in CROPS if seeds.get(c,0)>0 and crop_scores[c]>0]
                        if not alt:
                            action=['PASS'];op='PASS'
                        else:
                            crop=max(alt,key=lambda c:crop_scores[c]);action=['PLANT',crop]
                    if op=='PLANT':
                        seeds[crop]=max(0,seeds.get(crop,0)-1)
                        tiles[y][x]={'kind':'PLANT','crop':crop,'planted_day':day,'yield_units':0,'watered_today':False}
                        occupied+=1;counts[crop]=counts.get(crop,0)+1
                elif op=='DIG':tiles[y][x]=None
                elif op=='WATER':t['watered_today']=True
                elif op=='FEED':t['fed_today']=True;inv['WHEAT']-=1
                elif op=='CARE':t['cared_today']=True
                elif op=='FERTILIZE':t['fertilized_until_day']=day+2;inv['FERTILIZER']-=1
                elif op=='COLLECT_FERTILIZER':t['fertilizer_available']=False;inv['FERTILIZER']=inv.get('FERTILIZER',0)+1
                elif op=='HARVEST':
                    product=ANIMALS[t['animal']][1] if t.get('animal') else t['crop'];inv[product]=inv.get(product,0)+t['yield_units'];t['yield_units']=0
                    if t.get('crop') in ('WHEAT','CARROT','MELON'):
                        c=t['crop'];tiles[y][x]=None;occupied=max(0,occupied-1);counts[c]=max(0,counts.get(c,0)-1)
                elif op.startswith('BUILD_'):tiles[y][x]={'kind':op[6:]};occupied+=1
                elif op=='PLACE' and action[1] in ANIMALS:inv[action[1]]-=1;tiles[y][x]={'kind':'COOP' if action[1]=='GOOSE' else 'PASTURE','animal':action[1],'yield_units':0,'placed_day':day}
                elif op=='PICKUP':
                    k=action[1];amount=min(action[2],shed.get(k,0));shed[k]-=amount;inv[k]=inv.get(k,0)+amount
                elif op=='DROP':
                    room=max(0,100-sum(shed.values()))
                    for k,v in list(inv.items()):
                        take=min(room,v);shed[k]=shed.get(k,0)+take;room-=take;inv[k]=0
        actions.append(action)
    orders=[];cash=me['money'];reserve_feed=0 if day==29 else nlive*2
    def buy(order,cost):
        nonlocal cash
        if cost<=cash and len(orders)<10:orders.append(order);cash-=cost;return True
        return False
    empty_n=sum(1 for x,y in coords if tiles[y][x] is None)
    if CFG.get('bulk_wheat') and empty_n>CFG.get('empty_ok',2) and cash>50:
        want=min(8,empty_n,len(positions)+2)
        have=seeds.get('WHEAT',0)
        if have<want:
            qty=min(want-have,max(1,int((cash-50)//10)))
            buy(['BUY_SEED','WHEAT',qty],10*qty)
    sell_cap=CFG.get('sell_cap',6)
    sold=0
    for k,q in shed.items():
        if k in ANIMALS or sold>=sell_cap:continue
        sell=max(0,q-(reserve_feed if k=='WHEAT' else 0))
        if k=='FERTILIZER' and CFG.get('fert_drip'):
            sell=min(sell,CFG['fert_drip'])
        if day<29 and CFG.get('meter') and k in ('STRAWBERRY','MELON','MILK','WOOL'):
            sell=min(sell,CFG['meter'])
        if CFG.get('straw_hold_day') and k=='STRAWBERRY' and day<CFG['straw_hold_day']:
            sell=0
        if sell:orders.append(['SELL',k,sell]);sold+=1
    target_hands=min(CFG['hands'],4+day//CFG['hire_pace'])
    if CFG['workload_hiring']:
        workload=sum(counts.values())+nlive*3
        target_hands=min(CFG['hands'],max(4,2+int(workload/CFG['work_per_hand'])))
    if underfilled:target_hands=min(CFG['hands'],max(target_hands,4+min(day,6)))
    if day>=28:target_hands=CFG['hands'] if CFG['keep_late_hands'] else max(5,CFG['hands']-1)
    fib=[1,1,2,3,5,8,13,21,34,55,89,144]
    for h in range(me['hires_today'],target_hands):
        if hour>12 or cash<fib[min(h,len(fib)-1)]+40:break
        buy(['HIRE'],fib[min(h,len(fib)-1)])
    total_animals=nlive+sum(shed.get(a,0) for a in ANIMALS)+sum(inv.get(a,0) for inv in invs for a in ANIMALS)
    if day<12 and total_animals<min(CFG['animals'],5+day):
        populations={a:sum(tiles[y][x].get('animal')==a for x,y in animals)+shed.get(a,0)+sum(v.get(a,0) for v in invs) for a in ANIMALS}
        values={a:(max(prices[ANIMALS[a][1]],BASE[ANIMALS[a][1]]*.2)*(1+ANIMALS[a][3])/ANIMALS[a][3])/(1+populations[a]*.35) for a in ANIMALS}
        species=max(values,key=values.get)
        burst=CFG.get('sheep_burst',0)
        if burst and day==0 and hour<=1 and cash>ANIMALS['SHEEP'][0]*burst+200:
            buy(['BUY_ANIMAL','SHEEP',burst],ANIMALS['SHEEP'][0]*burst)
        elif cash>ANIMALS[species][0]+200:buy(['BUY_ANIMAL',species,1],ANIMALS[species][0])
    if nlive and hour<22 and (day<29 or not CFG['liquidate']):
        deficit=max(0,nlive*2-shed.get('WHEAT',0));qty=min(deficit,int(max(0,cash-50)//(prices['WHEAT']+2)))
        if qty:buy(['BUY_PRODUCT','WHEAT',qty],qty*(prices['WHEAT']+2))
    seed_n=CFG.get('seed_n',2)
    for c in sorted(CROPS,key=lambda c:-crop_scores[c]):
        if crop_scores[c]>0 and seeds.get(c,0)<seed_n and cash>100:
            qty=min(seed_n-seeds.get(c,0),max(1,int((cash-80)//CROPS[c][0])))
            buy(['BUY_SEED',c,qty],CROPS[c][0]*qty)
    landcount=len(me['unlocked_quadrants'])
    land_cap=CFG['land']
    if CFG.get('q3_day') and day>=CFG['q3_day']:
        land_cap=max(land_cap,3)
    if CFG.get('straw_drip') and landcount>=CFG.get('straw_drip_land',1) and 2<=day<=18 and crop_scores.get('STRAWBERRY',0)>0:
        if seeds.get('STRAWBERRY',0)<CFG['straw_drip']:
            buy(['BUY_SEED','STRAWBERRY',1],CROPS['STRAWBERRY'][0])
    if CFG.get('wheat_drip') and empty_n>CFG.get('empty_ok',2) and crop_scores.get('WHEAT',0)>0:
        if seeds.get('WHEAT',0)<CFG['wheat_drip']:
            buy(['BUY_SEED','WHEAT',1],10)
    if landcount<land_cap and day<CFG.get('land_deadline',18) and day>=CFG.get('land_min_day',0) and occupied/max(1,len(coords))>=CFG['land_util']:
        cost=[1000,2000,4000][landcount-1]
        if cash>cost+CFG['land_buffer']:buy(['BUY_LAND'],cost)
    return {'farmer':actions[0],'hands':actions[1:],'market':orders[:10]}
