Logic Tree Lending
Credit Strategy Framework

**Phân khúc**
18 sản phẩm

**Logic**
7 bước duyệt

**Timeline**
D+0 -> D+14

Credit Strategy Team • Q2 2026

# Logic Tree Lending — Credit Strategy

*Phân khúc khách hàng, logic xét duyệt và quy trình cho vay end-to-end*

## 1. Tổng quan

Tài liệu này tổng hợp khung phân tích thống nhất cho hoạt động cho vay — từ phân khúc khách hàng, ma trận sản phẩm, logic xét duyệt 7 bước, đến timeline xử lý hồ sơ end-to-end.

Phạm vi áp dụng cho cả phân khúc Cá nhân (Individual) và Doanh nghiệp (Corporate), với 18 sản phẩm cho vay đang vận hành.

### Key metrics

- 18 sản phẩm — tổng số loan products đang active
- 6 phân khúc — sub-segments active
- Biên lãi suất: 7.2% → 19.0%
- SLA trung bình: 14 ngày (D+0 → D+14)

## 2. Phân khúc khách hàng (Segment Tree)

Cấu trúc cây 3 cấp: Customer Type → Sub-Segment → Loan Products. Sơ đồ SmartArt dưới đây thể hiện hierarchy đầy đủ.

- KHÁCH HÀNG VAY(Lending segment)
  - Risk Mgmt
  - KH CÁ NHÂN
  - KH DOANH NGHIỆP
- Bank Products

*Hình 1. SmartArt Hierarchy — Cây phân khúc khách hàng vay*

## 3. Ma trận sản phẩm (Product Matrix)

Bảng dưới liệt kê 10 sản phẩm tiêu biểu với hạn mức, lãi suất và tỷ trọng portfolio (đầy đủ 18 sản phẩm có sẵn trong hệ thống core).

| Segment ID | Customer | Sub-Segment | Product | Min (VNDm) | Max (VNDm) | Rate | % Portfolio |
|---|---|---|---|---|---|---|---|
| IND-001 | Cá nhân | KH Ưu tiên | Vay mua nhà | 500 | 20,000 | 7.5% | 18% |
| IND-002 | Cá nhân | KH Ưu tiên | Vay mua xe | 200 | 3,000 | 8.2% | 6% |
| IND-003 | Cá nhân | KH Ưu tiên | Thẻ tín dụng | 10 | 500 | 18.0% | 4% |
| IND-004 | Cá nhân | KH Phổ thông | Vay tiêu dùng | 20 | 500 | 12.5% | 15% |
| IND-005 | Cá nhân | KH Phổ thông | Vay mua xe | 100 | 1,500 | 9.5% | 8% |
| IND-006 | Cá nhân | KH Phổ thông | Vay du học | 50 | 2,000 | 8.8% | 3% |
| CORP-004 | Doanh nghiệp | SME | Vay đầu tư | 2,000 | 50,000 | 9.0% | 8% |
| CORP-005 | Doanh nghiệp | SME | Tài trợ thương mại | 1,000 | 30,000 | 8.5% | 6% |
| CORP-007 | Doanh nghiệp | Large Corp | Syndicated Loan | 50,000 | 500,000 | 7.8% | 4% |
| CORP-008 | Doanh nghiệp | Large Corp | Project Finance | 100,000 | 1,000,000 | 8.0% | 2% |

*Bảng 1. Product Matrix — 10 sản phẩm tiêu biểu (Min/Max loan tính theo VND triệu)*

## 4. Logic xét duyệt tín dụng

Quy trình 7 bước: KYC → Credit Score → Income → DTI → Collateral → Risk Rating → Final Approval. Bất kỳ bước nào fail đều dẫn đến REJECT hoặc YÊU CẦU BỔ SUNG hồ sơ.

### 7 cổng quyết định

1. KYC — Hồ sơ pháp lý hợp lệ
2. Score — CIC ≥ 600, không nợ xấu
3. Income — TN ≥ 2× kỳ trả nợ
4. DTI — Debt-to-Income < 50%
5. Collateral — LTV ≤ 70–80%
6. Rating — Risk Rating ≥ BB
7. Final — Hội đồng tín dụng

### Sơ đồ luồng quyết định

Flowchart titled "Credit Decision Flow". Layout: vertical process flow.
- Nodes:
  - "START: Tiếp nhận hồ sơ" -> "B1. KYC & Hồ sơ pháp lý"
  - "B1. KYC & Hồ sơ pháp lý" -> "KYC hợp lệ?"
  - "KYC hợp lệ?" -> "REJECT: KYC fail" labeled "No"
  - "KYC hợp lệ?" -> "B2. Credit Score" labeled "Yes"
  - "B2. Credit Score" -> "Score ≥ 600?"
  - "Score ≥ 600?" -> "REJECT: Low score" labeled "No"
  - "Score ≥ 600?" -> "APPROVE → Giải ngân" labeled "Yes"

*Hình 2. Credit Decision Flow — Luồng quyết định cho vay (rút gọn)*

## 5. Timeline quy trình cho vay

End-to-end loan lifecycle from application to repayment. Lộ trình D+0 → M+1~N được chia thành 3 giai đoạn lớn: Pre-approval (D+0 → D+10), Disbursement (D+11 → D+14), và Monitoring (M+1 → N).

| Mốc | Giai đoạn | SLA | Phòng ban | Output |
|---|---|---|---|---|
| D+0 | Nộp hồ sơ | 1 ngày | Front Office | Hồ sơ vay |
| D+1~3 | Thẩm định hồ sơ | 3 ngày | Operations | Báo cáo KYC |
| D+4~7 | Đánh giá tín dụng | 4 ngày | Underwriting | Credit Memo |
| D+8~10 | Định giá TSĐB | 3 ngày | Appraisal | Báo cáo định giá |
| D+11~12 | Phê duyệt | 2 ngày | Credit Committee | Quyết định |
| D+13~14 | Giải ngân | 2 ngày | Operations | HĐ + tiền |
| M+1~N | Thu hồi nợ | Định kỳ | Collection | Lịch trả nợ |

*Bảng 2. Lending Process Timeline — Mốc, SLA và output cho từng giai đoạn*

## 6. Portfolio & Risk Metrics

## 6.1. Cơ cấu danh mục theo sản phẩm

Doughnut chart bên dưới thể hiện tỷ trọng % của từng sản phẩm trong tổng portfolio.

Chart titled "Portfolio Mix theo sản phẩm (% danh mục)". Layout: doughnut chart.
- Segments:
  - "Vay mua nhà": 18%
  - "Vay tiêu dùng": 15%
  - "Vay mua xe (IND)": 14%
  - "Vay tiêu dùng nhỏ": 9%
  - "SME Đầu tư": 7%
  - "Project/Syndicated": 6%
  - "Tài trợ TM": 4%
  - "Khác": 27%

*Biểu đồ 1. Portfolio Mix — Phân bổ % danh mục theo sản phẩm*

## 6.2. Phân bố Credit Score

Phần lớn khách hàng tập trung ở dải 600–699 (đạt ngưỡng pass tại bước B2). Khoảng 40 KH có điểm <600 sẽ bị reject tại bước Credit Score.

Chart titled "Phân bố Credit Score (CIC)".
- Y-axis label: "Số lượng khách hàng"
- X-axis label: "Credit Score Range"
- Data values per range:
  - <500: 12
  - 500-599: 28
  - 600-649: 95
  - 650-699: 142
  - 700-749: 88
  - 750+: 35
- Annotation: Vertical dashed red line labeled "Ngưỡng 600 (Pass/Fail)" separating the first two bars from the rest.

*Biểu đồ 2. Credit Score Distribution — Phân bố CIC score theo dải điểm*

## 7. Key Takeaways

1. Phân khúc rõ ràng — Cây 3 cấp giúp định nghĩa target customer cho từng sản phẩm, tránh chồng lấn và sai khẩu vị rủi ro.
2. Logic xét duyệt chuẩn hóa — 7 bước với threshold cụ thể: bất kỳ ai cũng có thể audit ngược lại quyết định approve/reject.
3. SLA đo được — Timeline D+0 → D+14 + thu hồi M+1~N cho phép set KPI cho từng phòng ban.

*Credit Strategy Team • Q2 2026 • credit-strategy@bank.vn*
