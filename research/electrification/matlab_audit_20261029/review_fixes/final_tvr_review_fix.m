% REVIEW CANDIDATE 2026-10-29: NOT YET RUN IN MATLAB.
% See the audit report and .diff; source snapshots are preserved in originals/.
clc
clear
%n=134062;
%t=[91499,92865,94279,95667,97020,98376,99528,100191,104731,113524,116319,116346,114865,114307,114375,114348,113467,106291,97358,94314,92769,91817,92769,91817];
%n=11367;
%t=[11367,11367,11423,12760,14371,14169,14184,12816,23277,36341,15403,11367,11396,11367,11373,11367,11395,11633,11367,11367,11367,11367,11367,11367];
n=40;
t=[40,40,40,40,40,40,40,40,40,40,40,47,40,40,44,48,48,40,40,40,41,40,40,40];

chargepile=40000;converting=30000;linefee=100;
c1=zeros(21,21);c2=zeros(21,21);c3=zeros(21,21);c4=zeros(21,21);c6=zeros(21,21);c7=zeros(21,21);c8=zeros(21,21);
agv=zeros(21,21);gp=zeros(21,21);aev=zeros(21,21);ep=zeros(21,21);hp=zeros(21,21);
lgv1=zeros(21,21);lgv2=zeros(21,21);lev1=zeros(21,21);lev2=zeros(21,21);
z1=zeros(1,21);z2=zeros(1,21);z3=zeros(1,24);
cgev=0.2;ctev=4.672;ccev=3.3;ccevp=0.5;cgicv=0.8;cticv=6.022;ccicv=3.3;ccicvp=0.5;
%cgev=0.2;ctev=4.672;ccev=3.3;ccevp=0.8;cgicv=0.8;cticv=6.022;ccicv=3.3;ccicvp=0.8;
r=0:0.05:1;u=0:0.05:1; u1=1; h1=0;
count1=0;count2=0;count3=0;count4=0;sumev=zeros(21,21);sumicv=zeros(21,21);lrev=zeros(21,21);lricv=zeros(21,21);lr=zeros(21,21);
for k=1:24  %某时刻停车场内数量
    z3(1,k)=t(1,k);
  for i=1:21 %假设停车场安装的一个桩车比
           z1(1,i)=r(1,i); 
    for j=1:21
           z2(1,j)=u(1,j);
              agv(i,j)=t(1,k).*u(1,j);
              gp(i,j)=n.*(1-r(1,i));
              aev(i,j)=t(1,k).*(1-u(1,j));
              ep(i,j)=n.*r(1,i);
              if r(1,i)<1
                    if agv(i,j) > gp(i,j)  %到达油车大于停车场油车车位
                        lgv1(i,j)=agv(i,j)-gp(i,j);  %准备容纳至混合车位的油车数量

                        if lgv1(i,j)>=n*r(1,i)*h1*u1  %油车剩余数量大于容纳油车车位
                           lgv2(i,j)=lgv1(i,j)-n*r(1,i)*h1*u1;  %到达油车经容纳后不得不离开数量
                            if aev(i,j)>ep(i,j)*(1-h1)*u1   %到达电车大于停车场电车车位
                            lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1; %准备容纳至混合车位的电车数量
                            lev2(i,j)=lev1(i,j);
                            count1=count1+1;
                            else
                            lev2(i,j)=0;
                            count2=count2+1;
                            end
                        c3(i,j)=lgv2(i,j)*(cgicv+cticv+ccicv*ccicvp)+lev2(i,j)*(cgev+ctev+ccev.*ccevp)+n.*r(1,i).*(chargepile+linefee+converting)/365/8/24;
                        sumev(i,j)=sumev(i,j)+lev2(i,j);
                        sumicv(i,j)=sumicv(i,j)+lgv2(i,j);
                        else   %油车剩余数量小于容纳油车车位 
                            lgv2(i,j)=0; 
                            hp(i,j)=n*r(1,i)*h1*u1-lgv1(i,j);  %剩余可容纳电车两用车位数量 
                            if aev(i,j)>ep(i,j)*(1-h1)*u1   %到达电车大于停车场电车车位
                            lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1; %准备容纳至混合车位的电车数量
                            lev2(i,j)=max(lev1(i,j)-hp(i,j),0);
                            count3=count3+1;
                            else
                            lev2(i,j)=0;
                            count4=count4+1;
                            end 
                        c3(i,j)=lgv2(i,j)*(cgicv+cticv+ccicv*ccicvp)+lev2(i,j)*(cgev+ctev+ccev.*ccevp)+n.*r(1,i).*(chargepile+linefee+converting)/365/8/24;
                        sumev(i,j)=sumev(i,j)+lev2(i,j);
                        sumicv(i,j)=sumicv(i,j)+lgv2(i,j);
                        end
                    else   %到达油车小于停车场油车车位
                            lgv2(i,j)=0;
                            hp(i,j)=n*r(1,i)*h1*u1;
                            if aev(i,j)>ep(i,j)   %到达电车大于停车场电车车位
                            lev1(i,j)=aev(i,j)-ep(i,j)*(1-h1)*u1; %准备容纳至混合车位的电车数量
                            lev2(i,j)=max(lev1(i,j)-hp(i,j),0);
                            count3=count3+1;
                            else
                            lev2(i,j)=0;
                            count4=count4+1;
                            end
                     c3(i,j)=lgv2(i,j)*(cgicv+cticv+ccicv*ccicvp)+lev2(i,j)*(cgev+ctev+ccev.*ccevp)+n.*r(1,i).*(chargepile+linefee+converting)/365/8/24;
                     sumev(i,j)=sumev(i,j)+lev2(i,j);
                     sumicv(i,j)=sumicv(i,j)+lgv2(i,j);
                    end
                   
              else
               if t(1,k)<n
                  c3(i,j)=n.*(chargepile+linefee+converting)/365/8/24;
               else
                 
                  c3(i,j)=n*(chargepile+linefee+converting)/365/8/24+(t(1,k)-n)*(cgicv+cticv+ccicv*ccicvp)*u(1,j)+(t(1,k)-n)*(cgev+ctev+ccev*ccevp)*(1-u(1,j));
                  sumicv(i,j)=sumicv(i,j)+(t(1,k)-n)*u(1,j);
                  sumev(i,j)=sumev(i,j)+(t(1,k)-n)*(1-u(1,j));
               end
              
               count1=count1+1;
              end
      c6(i,j)=c6(i,j)+c3(i,j);
      c8(i,j)=c6(i,j);
      
      
      
    end 
  end
  
end

% Daily rates: use daily demand; a zero-demand rate is undefined.
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

for o=1:size(c6,1)
    for p=1:size(c6,2)
      if c6(o,p)>c6(size(c6,1),p)
         c7(o,p)=c6(o,p)-c6(size(c6,1),p);
         c6(o,p)=NaN; % Display mask; unmodified costs remain in c8.
      end
    end
end
v=1-u;
[vv,rr]=meshgrid(v,r);
surf(vv,rr,c6)
colormap("turbo")
grid on
xlabel('EV proportion','FontName','Times New Roman')
ylabel('Pile-to-Parking Ratio','FontName','Times New Roman')
zlabel('Parking socail cost, RMB' ,'FontName','Times New Roman')

%surf(vv,rr,c7)
%colormap("turbo")
%grid on
%xlabel('EV proportion','FontName','Times New Roman')
%ylabel('Pile-to-Parking Ratio','FontName','Times New Roman')
%zlabel('difference, RMB' ,'FontName','Times New Roman')



