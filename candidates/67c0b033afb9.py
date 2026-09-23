"""Enhanced Game v15: v14 plus three searchable production mechanics -- survival-priced
watering, fertilizer across the whole yield window, and planting capped by watering
throughput. Each is off by default (survival_bias=0, fert_in_window=0, tiles_per_unit=0)
and those defaults reproduce v14 exactly, so the search can always recover it.
Motivation: analysis/REPORT_deployment_diagnosis.md. Std lib only."""
import copy

# A soft commitment, never an unconditional cached action. Reset every day/game.
_MEMORY = {}

CFG = {'animals': 16, 'hands': 12, 'land': 3, 'crop_bias': 1.5, 'care_bias': 1.3, 'fert_bias': 1.0, 'opponent_weight': 0.0, 'liquidate': True, 'drop_units': 5, 'drop_value': 1000000, 'cash_release': True, 'deposit_bias': 0.3, 'feed_fix': True, 'care_cap': 1.3, 'plant_floor': 40, 'hire_pace': 2, 'workload_hiring': False, 'work_per_hand': 8, 'keep_late_hands': True, 'land_util': 0.45, 'land_buffer': 700, 'commitment': 1.3, 'region_weight': 0.8, 'distance_weight': 0.65, 'dig_value': 45, 'animal_deadline': 16, 'land_deadline': 18, 'expansion_hands': 9, 'night_deposit': True, 'late_day': 24, 'crop_bias_late': 1.5, 'plant_floor_late': 40, 'deposit_bias_late': 0.3, 'strawberry_target': 30, 'survival_bias': 0.0, 'fert_in_window': 0, 'tiles_per_unit': 0, 'seed_stock': 2, 'land4_deadline': 18, 'early_cash_bias': 0.0, 'plant_urgency': 1.0, 'seed_fill': 0, 'cash_discount': 0.8, 'cash_patience': 8000.0}
CROPS={'WHEAT':(10,2,4,4),'CARROT':(20,2,3,3),'MELON':(80,10,12,6),'TOMATO':(50,8,11,4),'STRAWBERRY':(100,10,16,4)}
ANIMALS={'COW':(400,'MILK',8,2),'SHEEP':(500,'WOOL',6,3),'GOOSE':(300,'EGG',4,1)}
BASE={'WHEAT':25,'CARROT':35,'MELON':250,'TOMATO':60,'STRAWBERRY':120,'MILK':160,'WOOL':200,'EGG':50,'FERTILIZER':100}

def agent(obs):
    global _MEMORY
    tick=obs['day']*24+obs['hour']; player=obs['player']
    if _MEMORY.get('tick')!=tick-1 or _MEMORY.get('player')!=player or obs['hour']==0:
        _MEMORY={}
    old_jobs=_MEMORY.get('jobs',{}); jobs={}
    me=copy.deepcopy(obs['farms'][obs['player']]);pr=copy.deepcopy(obs['private'])
    tiles=me['tiles'];n=len(tiles);day=obs['day'];hour=obs['hour'];prices=obs['market']['prices'];remaining=30-day
    # Phase-dependent effective config. Overlays _mid/_late variants of a few
    # high-leverage keys once the game crosses day thresholds. Absent variants
    # fall back to the base key, so a config without them reproduces v1 exactly.
    P=dict(CFG)
    _phased=('crop_bias','plant_floor','deposit_bias','care_bias')
    if day>=CFG.get('mid_day',12):
        for _k in _phased:
            if _k+'_mid' in CFG: P[_k]=CFG[_k+'_mid']
    if day>=CFG.get('late_day',24):
        for _k in _phased:
            if _k+'_late' in CFG: P[_k]=CFG[_k+'_late']
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
    regions=sorted(set((x//center,y//center) for x,y in coords))
    # Stable spatial preference, with cross-region emergency work still allowed.
    homes={i:regions[i%len(regions)] for i in range(len(positions))}

    # Planting estimates account for crops already growing, maturity and expected market saturation.
    def crop_value(c):
        cost,first,peak,yld=CROPS[c]
        if day+first>=29 or (hour>=21 and c!='WHEAT'):return -1
        lifespan=min(peak,remaining-2)
        if c in ('TOMATO','STRAWBERRY'):
            interval=1 if c=='TOMATO' else 2;yld=max(0,min(4,1+(remaining-2-first)//interval))
        price=prices[c]
        if CFG['opponent_weight']>0:price=max(BASE[c]*.15,price-CFG['opponent_weight']*opponent_crops[c]*BASE[c]*.06)
        if c=='MELON':price=max(BASE[c]*.20,price-counts[c]*18)
        # Establish a large early strawberry crop before discounting for saturation.
        elif c=='STRAWBERRY' and counts['STRAWBERRY']>=CFG.get('strawberry_target',0):price=max(BASE[c]*.20,price-counts[c]*12)
        if c=='WHEAT' and nlive:price=max(price,32)
        style=CFG.get('crop_style','balanced')
        style_weight=1.0
        if style=='quick':style_weight=1.5 if c in ('WHEAT','CARROT') else .75
        if style=='orchard':style_weight=1.5 if c in ('TOMATO','STRAWBERRY') else .75
        # Discount a crop's revenue by how long we wait for it. Without this the
        # score is blind to WHEN cash arrives: MELON rates 133 against WHEAT's 17
        # purely on size, though a melon ties the tile ~12 days for one payment
        # while wheat first-yields on day 2 and can recycle three times in the same
        # span. Early cash is not merely nice, it compounds -- it is what buys the
        # hands, land and animals that produce everything later. The rank-2 leader's
        # trace is exactly that shape (analysis/REPORT_leader_gap.md): cash held at
        # 139/338/299 through day 7, then 6,876 by day 10, off 409 wheat and 222
        # carrot units a game, while we plant melon and earn nothing before day 10.
        # cash_discount=1.0 reproduces v15 exactly. Below 1 it prices impatience,
        # and the impatience fades as the bank fills, because waiting only costs
        # what the missing cash could have been reinvested in.
        _disc=CFG.get('cash_discount',1.)
        if _disc<1.:
            starved=max(0.,1.-me['money']/max(1.,CFG.get('cash_patience',8000.)))
            d=1.-(1.-_disc)*starved
            value=(yld*price*(d**first)-cost)/(lifespan+4)*P['crop_bias']*style_weight
        # Superseded by cash_discount, kept so existing rendered agents still load.
        _ecb=CFG.get('early_cash_bias',0.)
        if _ecb>0 and me['money']<2000:
            value*=1+_ecb*(1-me['money']/2000)/first
        return value
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
            score=value/(1+distance*CFG.get('distance_weight',.85))
            if key and day<29:
                if (target[0]//center,target[1]//center)!=homes[idx]:
                    score*=CFG.get('region_weight',1.)
                previous=old_jobs.get(idx)
                if previous and previous==(target,tuple(act)):
                    score*=CFG.get('commitment',1.)
            if score>best[0]:best=(score,target,(act,key))
        # Deposits make produce sellable before night and before the final turn.
        goods=sum(v for k,v in inv.items() if k not in ('WHEAT','FERTILIZER') and k not in ANIMALS)
        goods_value=sum(v*prices.get(k,0) for k,v in inv.items() if k not in ANIMALS and k!='WHEAT')
        deposit=(day==29 and hour+ds>=19 and sum(inv.values())>0) or goods>=CFG['drop_units'] or inv.get('FERTILIZER',0)>=4
        deposit=deposit or goods_value>=CFG['drop_value'] or (CFG['cash_release'] and me['money']<100 and goods_value>0)
        # Inventory is automatically deposited each night. Avoid unnecessary trips
        # when solvent and overnight storage is safe; final day has no such sale.
        if CFG.get('night_deposit',False) and day<29 and me['money']>=500:
            total_stock=sum(shed.values())+sum(sum(v.values()) for v in invs)
            if total_stock<80:deposit=False
        if day==29 and CFG['liquidate'] and sum(inv.values())>0:deposit=True
        if deposit and not carried:
            urgency=3000 if day==29 and hour+ds>=20 else max(90,goods_value*P['deposit_bias'])
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
        needed=sum(not tiles[y][x].get('fed_today') for x,y in animals)
        held_feed=sum(v.get('WHEAT',0) for v in invs)
        if nlive and inv.get('WHEAT',0)==0 and shed.get('WHEAT',0)>0 and hour<22 and (not CFG['feed_fix'] or (day<29 and needed>held_feed)):
            offer(210,nearest_shed,['PICKUP','WHEAT',min(4,shed['WHEAT'])])
        for x,y in coords:
            t=tiles[y][x];target=(x,y);key=('tile',x,y)
            if key in claimed:continue
            if isinstance(t,dict) and t.get('animal'):
                species=t['animal'];cost,product,first,interval=ANIMALS[species];price=prices[product]
                if not t.get('fed_today') and inv.get('WHEAT',0):offer(190+130*t.get('consecutive_unfed',0)+hour*3,target,['FEED'],key)
                if t.get('yield_units',0):offer(60+t['yield_units']*max(price,10)*.8,target,['HARVEST'],key)
                if not t.get('cared_today') and day<29 and t.get('yield_units',0)<5:offer(max(12,min(price,BASE[product]*CFG['care_cap']))*P['care_bias'],target,['CARE'],key)
                if t.get('fertilizer_available'):offer(max(40,prices['FERTILIZER'])*.85,target,['COLLECT_FERTILIZER'],key)
            elif isinstance(t,dict) and t.get('kind')=='PLANT':
                c=t['crop'];cost,first,peak,yld=CROPS[c];age=day-t['planted_day'];yield_units=t.get('yield_units',0)
                fertile=t.get('fertilized_until_day',-1)>=day
                # One-time crops: fertilizer doubles each watered day's gain, so with
                # fert_in_window it pays from the start of the window, not day first-1.
                _fstart=((peak+1)//2-1) if CFG.get('fert_in_window',0) else max(0,first-1)
                needs_fert=(c in ('TOMATO','STRAWBERRY') and age>=first-2) or (c not in ('TOMATO','STRAWBERRY') and age>=_fstart and age<peak)
                if not fertile and needs_fert and inv.get('FERTILIZER',0) and day<29:
                    offer(min(200,prices[c]*1.4)*CFG['fert_bias'],target,['FERTILIZE'],key)
                ready=yield_units>0 and age>=first and (c in ('TOMATO','STRAWBERRY') or age>=peak or yield_units>=6 or day==29)
                if ready:offer(100+yield_units*prices[c]*.55+(200 if day==29 else 0),target,['HARVEST'],key)
                if not t.get('watered_today') and not (day==29 and ready):
                    cu=t.get('consecutive_unwatered',0);_sb=CFG.get('survival_bias',0.)
                    if _sb<=0:
                        wv=95+hour*4+120*cu
                    else:
                        # Engine: two dry days destroy the tile, and one-time crops gain
                        # yield ONLY from watering inside [(peak+1)//2, peak]. Price the
                        # marginal unit and the replacement cost instead of a flat bonus.
                        wv=60+hour*3
                        if c in ('TOMATO','STRAWBERRY'):
                            left=max(0,min(4,1+(remaining-2-max(0,first-age))//(1 if c=='TOMATO' else 2))-yield_units)
                            replace=cost+left*prices[c]*.7
                        else:
                            if (peak+1)//2<=age<=peak and yield_units<yld:
                                wv+=(2 if fertile else 1)*prices[c]*.9
                            replace=cost+max(0,yld-yield_units)*prices[c]*.6
                        if cu>=1:wv=max(wv,_sb*replace)
                    offer(wv,target,['WATER'],key)
            elif t is None and not carried and hour<22 and (not CFG.get('tiles_per_unit',0) or occupied<len(positions)*CFG['tiles_per_unit']):
                available=[c for c in CROPS if seeds.get(c,0)>0 and crop_scores[c]>0]
                if available:
                    c=max(available,key=lambda c:crop_scores[c])
                    # plant_urgency scales a bare tile's bid against maintenance work.
                    # Measured over 35 real replays (2026-09-23): a rank-2 leader ends
                    # every day with ZERO bare owned tiles and plants 275 times a game;
                    # we sit on 20-40 bare tiles and plant ~100, because a PLANT bid of
                    # max(plant_floor, score) ~= 40-133 loses the per-unit auction to
                    # WATER (95+hour*4+120*dry) and FEED (190+) almost every turn. 1.0
                    # reproduces the old behaviour exactly.
                    offer(max(P['plant_floor'],crop_scores[c])*CFG.get('plant_urgency',1.),
                          target,['PLANT',c],key)
            elif isinstance(t,dict) and t.get('kind')=='WEED' and day<26:offer(CFG.get('dig_value',20),target,['DIG'],key)
        if best[1] is None:action=['PASS']
        else:
            _,target,(task,key)=best
            if key:claimed.add(key)
            if pos!=target:
                action=move(pos,target);jobs[idx]=(target,tuple(task))
            else:
                action=task;op=action[0];x,y=pos;t=tiles[y][x]
                # Project same-turn changes to coordinate later units and market orders.
                if op=='PLANT':
                    seeds[action[1]]-=1;tiles[y][x]={'kind':'PLANT','crop':action[1],'planted_day':day,'yield_units':0,'watered_today':False}
                elif op=='DIG':tiles[y][x]=None
                elif op=='WATER':t['watered_today']=True
                elif op=='FEED':t['fed_today']=True;inv['WHEAT']-=1
                elif op=='CARE':t['cared_today']=True
                elif op=='FERTILIZE':t['fertilized_until_day']=day+2;inv['FERTILIZER']-=1
                elif op=='COLLECT_FERTILIZER':t['fertilizer_available']=False;inv['FERTILIZER']=inv.get('FERTILIZER',0)+1
                elif op=='HARVEST':
                    product=ANIMALS[t['animal']][1] if t.get('animal') else t['crop'];inv[product]=inv.get(product,0)+t['yield_units'];t['yield_units']=0
                    if t.get('crop') in ('WHEAT','CARROT','MELON'):tiles[y][x]=None
                elif op.startswith('BUILD_'):tiles[y][x]={'kind':op[6:]}
                elif op=='PLACE' and action[1] in ANIMALS:inv[action[1]]-=1;tiles[y][x]={'kind':'COOP' if action[1]=='GOOSE' else 'PASTURE','animal':action[1],'yield_units':0,'placed_day':day}
                elif op=='PICKUP':
                    k=action[1];amount=min(action[2],shed.get(k,0));shed[k]-=amount;inv[k]=inv.get(k,0)+amount
                elif op=='DROP':
                    room=max(0,100-sum(shed.values()))
                    for k,v in list(inv.items()):
                        take=min(room,v);shed[k]=shed.get(k,0)+take;room-=take;inv[k]=0
        actions.append(action)
    orders=[];cash=me['money'];reserve_feed=0 if day==29 else nlive*2
    for k,q in shed.items():
        if k in ANIMALS:continue
        sell=max(0,q-(reserve_feed if k=='WHEAT' else 0))
        if sell:orders.append(['SELL',k,sell])
    # Spend only money already in the bank; each planned purchase reserves its cost.
    def buy(order,cost):
        nonlocal cash
        if cost<=cash and len(orders)<10:orders.append(order);cash-=cost;return True
        return False
    target_hands=min(CFG['hands'],4+day//CFG['hire_pace'])
    if CFG['workload_hiring']:
        workload=sum(counts.values())+nlive*3
        target_hands=min(CFG['hands'],max(4,2+int(workload/CFG['work_per_hand'])))
    if day>=28:target_hands=CFG['hands'] if CFG['keep_late_hands'] else max(5,CFG['hands']-1)
    fib=[1,1,2,3,5,8,13,21,34,55,89,144]
    for h in range(me['hires_today'],target_hands):
        if hour>12 or cash<fib[h]+40:break
        buy(['HIRE'],fib[h])
    # Include animals placed earlier in this same planned turn; otherwise one
    # disappears from the count and can trigger an unintended extra purchase.
    projected_live=sum(isinstance(tiles[y][x],dict) and bool(tiles[y][x].get('animal')) for x,y in coords)
    total_animals=projected_live+sum(shed.get(a,0) for a in ANIMALS)+sum(inv.get(a,0) for inv in invs for a in ANIMALS)
    if day<CFG.get('animal_deadline',12) and total_animals<min(CFG['animals'],5+day):
        populations={a:sum(tiles[y][x].get('animal')==a for x,y in animals)+shed.get(a,0)+sum(v.get(a,0) for v in invs) for a in ANIMALS}
        values={a:(max(prices[ANIMALS[a][1]],BASE[ANIMALS[a][1]]*.2)*(1+ANIMALS[a][3])/ANIMALS[a][3])/(1+populations[a]*.35) for a in ANIMALS}
        preference={'milk':'COW','wool':'SHEEP','eggs':'GOOSE'}.get(CFG.get('animal_style','balanced'))
        if preference:values[preference]*=1.8
        species=max(values,key=values.get)
        if cash>ANIMALS[species][0]+200:buy(['BUY_ANIMAL',species,1],ANIMALS[species][0])
    if nlive and hour<22 and (day<29 or not CFG['liquidate']):
        deficit=max(0,nlive*2-shed.get('WHEAT',0)-sum(v.get('WHEAT',0) for v in invs));qty=min(deficit,int(max(0,cash-50)//(prices['WHEAT']+2)))
        if qty:buy(['BUY_PRODUCT','WHEAT',qty],qty*(prices['WHEAT']+2))
    _stock=CFG.get('seed_stock',2)
    _fill=CFG.get('seed_fill',0)
    if _fill>0:
        # Demand-driven seed buying: stock against the tiles actually standing bare,
        # cheapest-value-per-cash first, instead of topping every crop up to the same
        # small number regardless of how much ground is empty. A flat seed_stock
        # structurally cannot fill land -- which is why raising it 2->6 previously
        # looked like it "hurt": it bought 6 of *everything*, so 600 cash of
        # strawberry seed starved the expansion it was supposed to feed, while the
        # cheap fast crops that actually fill tiles (WHEAT 10, CARROT 20) stayed
        # capped. The leader sells 409 wheat and 222 carrot units a game to our ~100
        # and ~22.
        bare=sum(1 for x,y in coords if tiles[y][x] is None)
        # Never buy seed for ground we are not allowed to plant: with tiles_per_unit
        # set, planting stops at what the hands can actually water, and seed bought
        # past that is cash burned for nothing.
        if CFG.get('tiles_per_unit',0):
            bare=max(0,min(bare,len(positions)*CFG['tiles_per_unit']-occupied))
        for c in sorted(CROPS,key=lambda c:-crop_scores[c]/CROPS[c][0]):
            if bare<=0:break
            if crop_scores[c]<=0:continue
            qty=min(bare,_fill)-seeds.get(c,0)
            while qty>0:
                if buy(['BUY_SEED',c,qty],CROPS[c][0]*qty):
                    bare-=qty;break
                qty//=2
    else:
        for c in sorted(CROPS,key=lambda c:-crop_scores[c]):
            if crop_scores[c]>0 and seeds.get(c,0)<_stock and cash>100:
                qty=_stock-seeds.get(c,0);buy(['BUY_SEED',c,qty],CROPS[c][0]*qty)
    landcount=len(me['unlocked_quadrants'])
    # Third/fourth quadrants require occupancy and staffing, not cash alone. The 4th
    # quadrant gets its own, later deadline: a single land_deadline covering every
    # purchase makes an early value structurally unreachable for landcount 3->4 (you
    # cannot own 75 tiles at land_util occupancy AND buy a 4th before the same cutoff
    # that governs the 2nd/3rd). Defaults to land_deadline, so omitting it reproduces
    # the single-deadline behavior exactly.
    staffed=(landcount<2 or len(positions)>=CFG.get('expansion_hands',9))
    deadline=CFG.get('land4_deadline',CFG.get('land_deadline',18)) if landcount>=3 else CFG.get('land_deadline',18)
    if landcount<CFG['land'] and day<deadline and staffed and occupied/max(1,len(coords))>=CFG['land_util']:
        cost=[1000,2000,4000][landcount-1]
        if cash>cost+CFG['land_buffer']:buy(['BUY_LAND'],cost)
    _MEMORY={'tick':tick,'player':player,'jobs':jobs}
    return {'farmer':actions[0],'hands':actions[1:],'market':orders[:10]}
