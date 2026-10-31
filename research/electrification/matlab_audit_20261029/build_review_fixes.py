"""Create review copies and unified diffs; preserve supplied files byte for byte.

Run only with explicit --out. These candidates have not been run in MATLAB.
NB arrivals, 50 scenarios, existing full-installation admission policy and the
two scripts' different costs/lifetimes are deliberately retained for review.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def replace_once(code, old, new):
    if code.count(old) != 1:
        raise ValueError('Expected exactly one occurrence: ' + old)
    return code.replace(old, new, 1)


def fix_v1(code):
    code = replace_once(code, 'lev1(i,j)=aev(i,j)-ep(i,j);',
                        'lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1;')
    code = replace_once(code, '(t(1,k)-n)*(cgev+ctev)*(1-u(1,j))',
                        '(t(1,k)-n)*(cgev+ctev+ccev*ccevp)*(1-u(1,j))')
    for line in ('lrev(i,j)=sumev(i,j)/(t(1,k)*(1-u(1,j)));',
                 'lricv(i,j)=sumicv(i,j)/(t(1,k)*u(1,j));',
                 'lr(i,j)=(sumev(i,j)+sumicv(i,j))/t(1,k);'):
        code = replace_once(code, line, '')
    rates = '''% Daily rates: use daily demand; a zero-demand rate is undefined.
den_ev_day = repmat(sum(t)*(1-u),length(r),1);
den_icv_day = repmat(sum(t)*u,length(r),1);
lrev(:) = NaN; lricv(:) = NaN;
valid_ev = den_ev_day>0; valid_icv = den_icv_day>0;
lrev(valid_ev) = sumev(valid_ev)./den_ev_day(valid_ev);
lricv(valid_icv) = sumicv(valid_icv)./den_icv_day(valid_icv);
lr = (sumev+sumicv)/sum(t);
[best_daily_cost,best_idx] = min(c8,[],1);
best_r = r(best_idx);
gap_to_full = c8-c8(end,:);

'''
    code = replace_once(code, 'for o=1:size(c6,1)', rates+'for o=1:size(c6,1)')
    code = replace_once(code, 'c6(o,p)=0;', 'c6(o,p)=NaN; % Display mask; unmodified costs remain in c8.')
    return code


def fix_v2(code):
    code = replace_once(code, 'lev1(i,j)=aev(i,j)-ep(i,j);',
                        'lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1;')
    code = replace_once(code, '(t_use-n)*(cgev+ctev+cfev)*(1-u_use)',
                        '(t_use-n)*(cgev+ctev+cfev+ccev*ccevp)*(1-u_use)')
    code = replace_once(code, 'c8_mc = zeros(21,21,nsim);', '''c8_mc = zeros(21,21,nsim);
ev_rejected_mc = zeros(21,21,nsim); ice_rejected_mc = zeros(21,21,nsim);
ev_demand_mc = zeros(21,21,nsim); ice_demand_mc = zeros(21,21,nsim);''')
    code = replace_once(code, '    eps0 = 1e-6;', '''    eps0 = 1e-6;
    ev_demand_day=zeros(21,21); ice_demand_day=zeros(21,21);''')
    code = replace_once(code, '            if rho_nev_min==0',
                        '            if rho_nev_min==0 || u(j0)==0 || u(j0)==1')
    code = replace_once(code, 'u_col = betarnd(alpha_u, beta_u, [21,1]);',
                        'u_col = repmat(betarnd(alpha_u, beta_u, [1,1]),21,1); % Same demand across candidate r.')
    code = replace_once(code, 'u_sim_mean(s,:) = mean(u2,1);',
                        'u_sim_mean(s,:) = u_sim_mean(s,:) + mean(u2,1)/24;')
    code = replace_once(code, 't_use = t1(k,1);     % <-- 这里改成只取 21×1 的第 i 个值',
                        't_use = t1(k,1);     % One arrival realization per hour, shared across r and u.')
    old_rates = '''                den_ev = max(t_use*(1-u_use), eps0);
                den_icv = max(t_use*u_use, eps0);
                den_all = max(t_use, eps0);

                lrev(i,j)=sumev(i,j)/den_ev;
                lricv(i,j)=sumicv(i,j)/den_icv;
                lr(i,j)=(sumev(i,j)+sumicv(i,j))/den_all;'''
    code = replace_once(code, old_rates, '''                ev_demand_day(i,j) = ev_demand_day(i,j)+t_use*(1-u_use);
                ice_demand_day(i,j) = ice_demand_day(i,j)+t_use*u_use;''')
    code = replace_once(code, '    c7_mc(:,:,s) = c7;', '''    c7_mc(:,:,s) = c6-c6(end,:); % Signed per-scenario gap, not an all-zero placeholder.
    ev_rejected_mc(:,:,s) = sumev; ice_rejected_mc(:,:,s) = sumicv;
    ev_demand_mc(:,:,s) = ev_demand_day; ice_demand_mc(:,:,s) = ice_demand_day;''')
    code = replace_once(code, 'c7 = mean(c7_mc,3);', '''gap_to_full = mean(c7_mc,3);
c7 = max(gap_to_full,0); % Positive part of mean gap, distinct from mean positive gap.''')
    code = replace_once(code, 'c8 = mean(c8_mc,3);', '''c8 = mean(c8_mc,3);
% Pooled daily rates across all scenarios. Zero-demand rates remain NaN.
ev_demand_total=sum(ev_demand_mc,3); ice_demand_total=sum(ice_demand_mc,3);
ev_rejected_total=sum(ev_rejected_mc,3); ice_rejected_total=sum(ice_rejected_mc,3);
lrev(:)=NaN; lricv(:)=NaN;
valid_ev=ev_demand_total>0; valid_icv=ice_demand_total>0;
lrev(valid_ev)=ev_rejected_total(valid_ev)./ev_demand_total(valid_ev);
lricv(valid_icv)=ice_rejected_total(valid_icv)./ice_demand_total(valid_icv);
lr=(ev_rejected_total+ice_rejected_total)./(ev_demand_total+ice_demand_total);''')
    code = replace_once(code, 'c6(o,p) = 0;', 'c6(o,p) = NaN; % Display mask; c8 retains all raw costs.')
    code = replace_once(code, 'c7_std = std(c7_mc,0,3);',
                        'gap_to_full_std = std(c7_mc,0,3); % Descriptive spread, not a confidence interval.')
    start = code.index('%% ================= 每一列(u)的最优成本')
    end = code.index('%% ================= 输出检查', start)
    code = code[:start]+'''%% Compare the passive EV-matching policy with the grid optimum.
r_grid = 0:0.05:1;
u_grid = 0:0.05:1;
ev_share_grid = 1-u_grid;
[min_c8_each_u,min_row_idx] = min(c8,[],1);
best_r_each_u = r_grid(min_row_idx);
passive_row_idx = length(r_grid):-1:1;
c8_at_r_eq_ev = c8(sub2ind(size(c8),passive_row_idx,1:length(u_grid)));
c8_gap = c8_at_r_eq_ev-min_c8_each_u;
result_table = table(u_grid(:),ev_share_grid(:),min_c8_each_u(:),best_r_each_u(:), ...
    c8_at_r_eq_ev(:),c8_gap(:), ...
    'VariableNames',{'u_ice','ev_share','min_c8','best_r','c8_at_r_eq_ev','gap_from_best'});
writetable(result_table,'c8_ev_passive_comparison_review.xlsx');

'''+code[end:]
    code = replace_once(code, '    t = (j-1)/(n_u-1);   % t=0 对应 EV=1 (u=0)，t=1 对应 EV=0 (u=1)',
                        '    blend = (j-1)/(n_u-1); % Preserve the baseline arrival vector t.')
    code = replace_once(code, 'colors(j,:) = (1-t)*[0, 0, 0.7] + t*[0.6, 0.9, 1];',
                        'colors(j,:) = (1-blend)*[0, 0, 0.7] + blend*[0.6, 0.9, 1];')
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = {'status': 'Review candidates; native MATLAB execution has not been performed.', 'files': []}
    for name, fun in [('final_tvr.m', fix_v1), ('final_tvr_v2_fluc_re.m', fix_v2)]:
        path = HERE/'originals'/name
        original = path.read_text('utf-8-sig')
        fixed = ('% REVIEW CANDIDATE 2026-10-29: NOT YET RUN IN MATLAB.\n'
                 '% See the audit report and .diff; source snapshots are preserved in originals/.\n'+fun(original))
        target = args.out/(path.stem+'_review_fix.m')
        target.write_text(fixed, encoding='utf-8')
        patch = ''.join(difflib.unified_diff(original.splitlines(True),fixed.splitlines(True),
                                           fromfile='originals/'+name,tofile=target.name))
        target.with_suffix('.diff').write_text(patch, encoding='utf-8')
        manifest['files'].append({'source': name, 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                  'candidate': target.name, 'candidate_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
    (args.out/'review_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
