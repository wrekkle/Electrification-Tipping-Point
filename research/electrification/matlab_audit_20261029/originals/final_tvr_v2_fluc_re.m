clc
clear


n=10786;
%t = [6368.64, 6060.48, 6137.52, 6034.8, 5880.72, 5880.72, 5906.4, 5829.36, 5803.68, 6137.52, 6805.2, 7087.68, 7216.08, 7267.44, 7087.68, 7241.76, 7832.4, 7883.76, 8474.4, 8346, 7498.56, 6548.4, 6574.08, 6188.88];
t=[10786, 10786, 10786, 10786, 10786, 10786, 10786, 10786, 10786, 10786, 10786, 12673.55, 10786, 10786, 11864.6, 12943.2, 12943.2, 10786, 10786, 10786, 11055.65, 10786, 10786, 10786];% 基准到达量（代表曲线）




%聚类
%t=[40,40,40,40,40,40,40,40,40,40,40,47,40,40,44,48,48,40,40,40,41,40,40,40];
%最多
%t=[40,40,40,40,40,40,40,40,40,40,40,46,40,47,51,40,45,40,40,41,48,40,40,40];
power = 50;
installationcost = power*1000*1.2;

%% ================= 实际数据拟合得到的波动参数 =================
% ---------- A. 新能源车占比波动 ----------
% 来源：你贴出的 20个停车场 × 24小时 新能源车占比数据
% rho_nev(h) = var_nev(h) / [ mean_nev(h)*(1-mean_nev(h)) ]
%rho_nev = [0.14 0.2081 0.155 0.18 0.265 0.2037 0.21 0.0668 0.048 0.0567 0.0468 0.0741 0.1032 0.0888 0.0630 0.0719 0.0654 0.0672 0.0841 0.0937 0.0844 0.0817 0.1067 0.1234];
%rho_nev_min = min (rho_nev);
%rho_nev = [0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09 0.09];
%rho_nev =[0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05];
%rho_nev =[0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25];
rho_nev_min =0.09;
% ---------- B. 到达数量波动 ----------
% 来源：你贴出的 20个停车场 × 24小时 总到达量数据
% od_arr(h) = var_arr(h) / mean_arr(h)
%od_arr = [21.1933 9.2593 7.9630 7.3070 12.5475 25.7370 39.0861 53.7587 198.3645 145.0033 89.9855 61.3563 45.9025 43.1019 74.6561 54.4997 38.2346 38.6662 66.6540 49.7173 40.1334 44.7547 35.0157 22.0484];
%od_arr = [42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42 42];
%od_arr = [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10];
%od_arr = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100];
%od_arr_min = min (od_arr);
od_arr_min =42;
%% ================= 固定概率分位抽样：时间成本与抱怨概率 =================
mu_ct  = 2.9852;
sig_ct = 0.8477;

alpha_cp = 6.938;
beta_cp  = -2.324;

nsim = 50;

rng(1);
u_draw = ((1:nsim) - 0.5) / nsim;
u_draw = u_draw(randperm(nsim));
ctev_draws = logninv(u_draw, mu_ct, sig_ct);

c6_mc = zeros(21,21,nsim);
c7_mc = zeros(21,21,nsim);
c8_mc = zeros(21,21,nsim);

ccevp_draws = zeros(nsim,1);
ccicvp_draws = zeros(nsim,1);
cticv_draws = zeros(nsim,1);

% 检查随机输入
u_sim_mean = zeros(nsim,21);
t_sim_mean = zeros(nsim,24);

for s = 1:nsim

    %% ================= 每次模拟的异质性参数 =================
    ctev = ctev_draws(s)*6.81/60;
    cticv = ctev;

    ccevp = 1/(1+exp(alpha_cp + beta_cp*log(ctev/6.81*60)));
    ccicvp = 1/(1+exp(alpha_cp + beta_cp*log(cticv/6.81*60)));

    ccevp_draws(s) = ccevp;
    ccicvp_draws(s) = ccicvp;
    cticv_draws(s) = cticv;

    %% ================= 主模型变量 =================
    c1=zeros(21,21);c2=zeros(21,21);c3=zeros(21,21);c4=zeros(21,21);c6=zeros(21,21);c7=zeros(21,21);c8=zeros(21,21);
    agv=zeros(21,21);gp=zeros(21,21);aev=zeros(21,21);ep=zeros(21,21);hp=zeros(21,21);
    lgv1=zeros(21,21);lgv2=zeros(21,21);lev1=zeros(21,21);lev2=zeros(21,21);
    z1=zeros(1,21);z2=zeros(1,21);z3=zeros(1,24);

    cgev=0.085;
    cfev=0.68;ccev=1.5;
    cgicv=0.24;
    cficv=2.72;ccicv=1.5;

    r=0:0.05:1;
    u=0:0.05:1;      % 油车占比策略网格
    h1=0;
    u1=1;
    eps0 = 1e-6;

    count1=0;count2=0;count3=0;count4=0;
    sumev=zeros(21,21);sumicv=zeros(21,21);lrev=zeros(21,21);lricv=zeros(21,21);lr=zeros(21,21);

    %% ========== 先生成整天24小时的扰动后到达量 t1 ==========
    t1 = zeros(24,1);

    for kk = 1:24
        mu_t = max(t(1,kk), eps0);
        if od_arr_min == 0
            t1(kk,1)=t(1,kk);
        else 
            var_t = max(mu_t * od_arr_min, mu_t + eps0);   % 用最小波动值
            R_t = mu_t^2 / max(var_t - mu_t, eps0);
            P_t = R_t / (R_t + mu_t);
            % 每个小时只生成一个扰动值
            t1(kk,1) = nbinrnd(R_t, P_t, [1,1]);
        end
    end
    for k=1:24
        z3(1,k)=t(1,k);

        %% ========== 2) 新能源车占比扰动：仍按 21×21 生成 ==========
        % 基准均值由策略 1-u(j) 决定

        u2 = zeros(21,21);
        share_ev_mat = zeros(21,21);

        for j0 = 1:21
            % 第 j 列的油车占比均值必须就是策略值 u(j0)
            mu_u_base = u(j0);
            
            if rho_nev_min==0
               u_col = repmat(u(j0),21,1);
            else
                mu_u_base = min(max(mu_u_base,1e-4),1-1e-4);
                % 波动强度：使用最小相对波动值
                var_u = rho_nev_min * mu_u_base * (1-mu_u_base);
                var_u = min(var_u, 0.95 * mu_u_base * (1-mu_u_base));
                var_u = max(var_u, 1e-6);

                phi_u = mu_u_base*(1-mu_u_base)/var_u - 1;
                phi_u = max(phi_u, 2);

                alpha_u = mu_u_base * phi_u;
                beta_u  = (1-mu_u_base) * phi_u;
                % 直接对油车占比 u 抽样
                u_col = betarnd(alpha_u, beta_u, [21,1]);
            end
            u2(:,j0) = u_col;
            % 新能源车占比只是 1-u
            share_ev_mat(:,j0) = 1 - u_col;
        end
   
        u_sim_mean(s,:) = mean(u2,1);
        t_sim_mean(s,:) =t1(:)';

        for i=1:21
            z1(1,i)=r(1,i);

            for j=1:21
                u_use = u2(i,j);     % 当前格点实际油车占比
                t_use = t1(k,1);     % <-- 这里改成只取 21×1 的第 i 个值

                z2(1,j)=u_use;

                agv(i,j)=t_use*u_use;
                gp(i,j)=n*(1-r(1,i));
                aev(i,j)=t_use*(1-u_use);
                ep(i,j)=n*r(1,i);

                if r(1,i)<1
                    if agv(i,j) > gp(i,j)
                        lgv1(i,j)=agv(i,j)-gp(i,j);

                        if lgv1(i,j)>=n*r(1,i)*h1*u1
                            lgv2(i,j)=lgv1(i,j)-n*r(1,i)*h1*u1;

                            if aev(i,j)>ep(i,j)*(1-h1)*u1
                                lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1;
                                lev2(i,j)=lev1(i,j);
                                count1=count1+1;
                            else
                                lev2(i,j)=0;
                                count2=count2+1;
                            end

                            c3(i,j)=lgv2(i,j)*(cgicv+cticv+cficv+ccicv*ccicvp) ...
                                   +lev2(i,j)*(cgev+ctev+cfev+ccev*ccevp) ...
                                   +n*r(1,i)*(installationcost)/365/5/24;
                            sumev(i,j)=sumev(i,j)+lev2(i,j);
                            sumicv(i,j)=sumicv(i,j)+lgv2(i,j);

                        else
                            lgv2(i,j)=0;
                            hp(i,j)=n*r(1,i)*h1*u1-lgv1(i,j);

                            if aev(i,j)>ep(i,j)*(1-h1)*u1
                                lev1(i,j)=aev(i,j)-ep(i,j);
                                lev2(i,j)=max(lev1(i,j)-hp(i,j),0);
                                count3=count3+1;
                            else
                                lev2(i,j)=0;
                                count4=count4+1;
                            end

                            c3(i,j)=lgv2(i,j)*(cgicv+cticv+cficv+ccicv*ccicvp) ...
                                   +lev2(i,j)*(cgev+ctev+cfev+ccev*ccevp) ...
                                   +n*r(1,i)*(installationcost)/365/5/24;
                            sumev(i,j)=sumev(i,j)+lev2(i,j);
                            sumicv(i,j)=sumicv(i,j)+lgv2(i,j);
                        end

                    else
                        lgv2(i,j)=0;
                        hp(i,j)=n*r(1,i)*h1*u1;

                        if aev(i,j)>ep(i,j)
                            lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1;
                            lev2(i,j)=max(lev1(i,j)-hp(i,j),0);
                            count3=count3+1;
                        else
                            lev2(i,j)=0;
                            count4=count4+1;
                        end

                        c3(i,j)=lgv2(i,j)*(cgicv+cticv+cficv+ccicv*ccicvp) ...
                               +lev2(i,j)*(cgev+ctev+cfev+ccev*ccevp) ...
                               +n*r(1,i)*(installationcost)/365/5/24;
                        sumev(i,j)=sumev(i,j)+lev2(i,j);
                        sumicv(i,j)=sumicv(i,j)+lgv2(i,j);
                    end

                else
                    if t_use<n
                        c3(i,j)=n*(installationcost)/365/5/24;
                    else
                        c3(i,j)=n*(installationcost)/365/5/24 ...
                               +(t_use-n)*(cgicv+cticv+cficv+ccicv*ccicvp)*u_use ...
                               +(t_use-n)*(cgev+ctev+cfev)*(1-u_use);
                        sumicv(i,j)=sumicv(i,j)+(t_use-n)*u_use;
                        sumev(i,j)=sumev(i,j)+(t_use-n)*(1-u_use);
                    end
                    count1=count1+1;
                end

                c6(i,j)=c6(i,j)+c3(i,j);
                c8(i,j)=c6(i,j);

                den_ev = max(t_use*(1-u_use), eps0);
                den_icv = max(t_use*u_use, eps0);
                den_all = max(t_use, eps0);

                lrev(i,j)=sumev(i,j)/den_ev;
                lricv(i,j)=sumicv(i,j)/den_icv;
                lr(i,j)=(sumev(i,j)+sumicv(i,j))/den_all;
            end
        end
    end

    c6_mc(:,:,s) = c6;
    c7_mc(:,:,s) = c7;
    c8_mc(:,:,s) = c8;
end

%% ================= Monte Carlo 汇总 =================
c6 = mean(c6_mc,3);
c7 = mean(c7_mc,3);
c8 = mean(c8_mc,3);

for o = 1:size(c6,1)
    for p = 1:size(c6,2)
        c8(o,p) = c6(o,p);
        benchmark = c6(end,p);
        if c6(o,p) > benchmark
           c7(o,p) = c6(o,p) - benchmark;
           c6(o,p) = 0;
        end
    end
end

c6_std = std(c6_mc,0,3);
c7_std = std(c7_mc,0,3);
c8_std = std(c8_mc,0,3);

%% ================= 每一列(u)的最优成本、r=u成本及差值 =================
r_grid = 0:0.05:1;
u_grid = 0:0.05:1;

% 1) 每一列最小 c8 及对应 r
[min_c8_each_u, min_row_idx] = min(c8, [], 1);
best_r_each_u = r_grid(min_row_idx);

% 2) 每一列在 r=u 时的成本
% 因为 r_grid 和 u_grid 都是 0:0.05:1，行列索引一一对应
diag_idx = 1:length(u_grid);
c8_at_r_eq_u = c8(sub2ind(size(c8), diag_idx, diag_idx));

% 3) 差值：r=u 成本 - 该列最优成本
c8_gap = c8_at_r_eq_u - min_c8_each_u;

% 4) 汇总成表
result_table = table( ...
    u_grid(:), ...
    min_c8_each_u(:), ...
    best_r_each_u(:), ...
    c8_at_r_eq_u(:), ...
    c8_gap(:), ...
    'VariableNames', {'u', 'min_c8', 'best_r', 'c8_at_r_eq_u', 'gap_from_best'} ...
);

% 保存到 Excel
writetable(result_table, 'c8_u_comparison.xlsx');

%% ================= 输出检查 =================
fprintf('Monte Carlo simulations = %d\n', nsim);
fprintf('mean(log(ctev_draws)) = %.4f\n', mean(log(ctev_draws)));
fprintf('std(log(ctev_draws))  = %.4f\n', std(log(ctev_draws)));
fprintf('mean(ctev_draws)      = %.4f RMB/hour\n', mean(ctev_draws));
fprintf('median(ctev_draws)    = %.4f RMB/hour\n', median(ctev_draws));
fprintf('mean(ccevp_draws)     = %.4f\n', mean(ccevp_draws));
fprintf('mean(ccicvp_draws)    = %.4f\n', mean(ccicvp_draws));



%% ================= 绘制C8随r变化的折线图（步长0.2，r=1用点表示，蓝色渐变）=================
r_full = 0:0.05:1;          % 原始网格（21个点）
u_full = 0:0.05:1;          % 原始网格
r_plot = 0:0.05:1;           % 要绘制的r值（7个点）
u_plot = [0,0.2,0.4,0.6,0.8,1];                % 要绘制的u值（去掉0.95，保留6个）

% 找到r_plot和u_plot在原始网格中的索引
[~, idx_r] = ismember(r_plot, r_full);
[~, idx_u] = ismember(u_plot, u_full);

if any(idx_r == 0) || any(idx_u == 0)
    error('选定的r或u值不在原始网格中，请检查步长设置。');
end

% 提取子矩阵：行对应r_plot，列对应u_plot
c8_plot = c8(idx_r, idx_u);

% 计算对应的EV比例
EV_prop = 1 - u_plot;       % EV proportion = 1 - u

% 定义蓝色渐变：EV高（u小）用深蓝，EV低（u大）用浅蓝
n_u = length(u_plot);
colors = zeros(n_u, 3);
% 深蓝 [0, 0, 0.7]  浅蓝 [0.6, 0.9, 1]  可根据需要调整
for j = 1:n_u
    t = (j-1)/(n_u-1);   % t=0 对应 EV=1 (u=0)，t=1 对应 EV=0 (u=1)
    colors(j,:) = (1-t)*[0, 0, 0.7] + t*[0.6, 0.9, 1];
end

% 绘图
figure;
hold on;
for j = 1:n_u
    % 绘制前6个点的连线（r=0到0.95）
    plot(r_plot(1:20), c8_plot(1:20,j), 'Color', colors(j,:), 'LineWidth', 1, ...
        'DisplayName', sprintf('EV proportion= %.1f', EV_prop(j)));
    % 用散点绘制最后一个点（r=1），隐藏图例项
    scatter(r_plot(21), c8_plot(21,j), 50, colors(j,:), 'filled', 'Marker', 'o', ...
        'HandleVisibility', 'off');
end
hold off;
xlabel('Pile-to-Parking Ratio','FontSize', 13);
ylabel('Parking Social Cost, RMB','FontSize', 13);
title('');
legend('Location', 'best','FontSize', 13);
set(gca, 'FontSize', 13); 
grid on;




