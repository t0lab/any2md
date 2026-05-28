# Logic Tree — Lending Customer Segmentation & Process

Workbook gồm 3 sheet mô tả: phân khúc khách hàng vay (Segment Tree), logic xét duyệt tín dụng (Logic Cus) và dòng thời gian quy trình cho vay (Timeline).

---

## Sheet 1: Segment Tree

**SEGMENT TREE - PHÂN KHÚC KHÁCH HÀNG VAY**
Bảng phân khúc khách hàng và sản phẩm cho vay tương ứng.

### Bảng phân khúc khách hàng & sản phẩm

| Segment ID | Customer Type | Sub-Segment | Product | Min Loan (VND mm) | Max Loan (VND mm) | Interest Rate | % Portfolio |
|---|---|---|---|---|---|---|---|
| IND-001 | Cá nhân | KH Ưu tiên | Vay mua nhà | 500 | 20000 | 7.5% | 18% |
| IND-002 | Cá nhân | KH Ưu tiên | Vay mua xe | 200 | 3000 | 8.2% | 6% |
| IND-003 | Cá nhân | KH Ưu tiên | Thẻ tín dụng | 10 | 500 | 18.0% | 4% |
| IND-004 | Cá nhân | KH Phổ thông | Vay tiêu dùng | 20 | 500 | 12.5% | 15% |
| IND-005 | Cá nhân | KH Phổ thông | Vay mua xe | 100 | 1500 | 9.5% | 8% |
| IND-006 | Cá nhân | KH Phổ thông | Vay du học | 50 | 2000 | 8.8% | 3% |
| IND-007 | Cá nhân | KH Thu nhập thấp | Vay tín chấp nhỏ | 5 | 100 | 16.5% | 5% |
| IND-008 | Cá nhân | KH Thu nhập thấp | Vay trả góp | 10 | 200 | 14.5% | 4% |
| IND-009 | Cá nhân | KH Thu nhập thấp | Microloan | 1 | 50 | 19.0% | 2% |
| CORP-001 | Doanh nghiệp | Micro Business | Vay vốn lưu động | 100 | 2000 | 10.5% | 5% |
| CORP-002 | Doanh nghiệp | Micro Business | Vay TS cố định | 200 | 5000 | 10.0% | 3% |
| CORP-003 | Doanh nghiệp | Micro Business | OD ngắn hạn | 50 | 1000 | 11.5% | 2% |
| CORP-004 | Doanh nghiệp | SME | Vay đầu tư | 2000 | 50000 | 9.0% | 8% |
| CORP-005 | Doanh nghiệp | SME | Tài trợ thương mại | 1000 | 30000 | 8.5% | 6% |
| CORP-006 | Doanh nghiệp | SME | Vay dự án | 5000 | 100000 | 9.5% | 4% |
| CORP-007 | Doanh nghiệp | Large Corporate | Syndicated Loan | 50000 | 500000 | 7.8% | 4% |
| CORP-008 | Doanh nghiệp | Large Corporate | Project Finance | 100000 | 1000000 | 8.0% | 2% |
| CORP-009 | Doanh nghiệp | Large Corporate | Trade Finance | 20000 | 300000 | 7.2% | 1% |
| **TOTAL** | | | | | | | **=SUM(H5:H22) = 100%** |

### Sơ đồ cây phân khúc (SmartArt Diagram)

*(SmartArt được nhúng trong sheet — có thể click chọn và chỉnh sửa qua SmartArt Tools)*

- **KHÁCH HÀNG VAY (Lending Customers)**
  - **KH CÁ NHÂN (Individual)**
    - **KH Ưu tiên (Priority)**
      - Vay mua nhà
      - Vay mua xe
      - Thẻ tín dụng
    - **KH Phổ thông (Mass)**
      - Vay tiêu dùng
      - Vay mua xe
      - Vay du học
    - **KH TN thấp (Low-income)**
      - Vay tín chấp nhỏ
      - Vay trả góp
      - Microloan
  - **KH DOANH NGHIỆP (Corporate)**
    - **Micro Business**
      - Vay vốn lưu động
      - Vay TS cố định
      - OD ngắn hạn
    - **SME**
      - Vay đầu tư
      - Tài trợ thương mại
      - Vay dự án
    - **Large Corporate**
      - Syndicated Loan
      - Project Finance
      - Trade Finance

---

## Sheet 2: Logic Cus

**LOGIC CUSTOMER - QUY TRÌNH XÉT DUYỆT TÍN DỤNG**
Bảng logic xét duyệt khách hàng từng bước & quyết định Approve / Reject.

### Bảng các bước xét duyệt

| Step | Decision Point | Tiêu chí (Criteria) | Threshold | Pass Action | Fail Action | Owner |
|---|---|---|---|---|---|---|
| B1 | KYC & Hồ sơ pháp lý | CMND/CCCD hợp lệ + Hộ khẩu + Lý lịch | Đầy đủ + hợp lệ | → Sang B2 | REJECT: KYC fail | Front Office |
| B2 | Credit Score (CIC) | CIC score + lịch sử nợ quá hạn | Score ≥ 600 & ko nợ xấu | → Sang B3 | REJECT: Low score | Credit Bureau |
| B3 | Xác minh thu nhập | Bảng lương / Sao kê 6 tháng | TN ≥ 2x kỳ trả | → Sang B4 | Yêu cầu bổ sung | Underwriter |
| B4 | Debt-to-Income (DTI) | (Tổng nợ phải trả) / (Thu nhập) | DTI < 50% | → Sang B5 | REJECT: High DTI | Underwriter |
| B5 | Đánh giá TSĐB | Loại TS + giá trị thẩm định | LTV ≤ 70-80% | → Sang B6 | Giảm hạn mức | Appraiser |
| B6 | Risk Rating tổng hợp | Tổng hợp: PD, LGD, EAD | Rating ≥ BB | → Sang B7 | Escalate hội đồng | Risk Mgmt |
| B7 | Phê duyệt cuối | Hội đồng tín dụng / DPCA | Theo phân cấp | APPROVE → Giải ngân | REJECT: Final | Credit Committee |

### Sơ đồ logic quyết định (Decision Flow Diagram)

**LOGIC CUSTOMER - CREDIT DECISION FLOW**

Luồng quyết định trong sheet được vẽ dưới dạng flowchart với các hộp xử lý (chữ nhật) và hộp điều kiện (kim cương):

- **START: Tiếp nhận hồ sơ vay**
- → **B1. Định danh KYC & hồ sơ pháp lý**
- → Diamond: **KYC hợp lệ?**
  - No → **REJECT: KYC fail**
  - Yes → **B2. Kiểm tra CIC / Credit Score**
- → Diamond: **Score ≥ 600?**
  - No → **REJECT: Low score**
  - Yes → **B3. Xác minh thu nhập & DTI**, song song nhánh trái: **B4. Đánh giá TSĐB (nếu có)** → **B5. Tính LTV & Risk Rating**
- → Diamond: **DTI < 50%?**
  - No → **REJECT: High DTI**
  - Yes → Diamond: **Tổng hợp: Approve?** (gộp với nhánh B5)
    - Yes → **APPROVE → Giải ngân**
    - No → **REJECT → Thông báo KH**

---

## Sheet 3: Timeline

**TIMELINE - QUY TRÌNH CHO VAY (End-to-End)**
Dòng thời gian từ lúc nhận hồ sơ đến lúc thu hồi nợ.

### Bảng timeline

| Mốc | Giai đoạn | Hoạt động chính | SLA | Phòng ban | Output |
|---|---|---|---|---|---|
| D+0 | Nộp hồ sơ | KH nộp đơn vay + giấy tờ tùy thân | 1 ngày | Front Office | Hồ sơ vay |
| D+1~3 | Thẩm định hồ sơ | KYC, kiểm tra hồ sơ pháp lý | 3 ngày | Operations | Báo cáo KYC |
| D+4~7 | Đánh giá tín dụng | CIC, Credit Score, xác minh thu nhập | 4 ngày | Underwriting | Credit Memo |
| D+8~10 | Định giá TSĐB | Đánh giá tài sản bảo đảm + LTV | 3 ngày | Appraisal | Báo cáo định giá |
| D+11~12 | Phê duyệt | Hội đồng tín dụng ra quyết định | 2 ngày | Credit Committee | Quyết định phê duyệt |
| D+13~14 | Giải ngân | Ký HĐ tín dụng + chuyển tiền | 2 ngày | Operations | HĐ + tiền |
| M+1~N | Thu hồi nợ | Theo dõi kỳ trả, thu lãi + gốc | Định kỳ | Collection | Lịch trả nợ |

### Biểu đồ timeline

**LENDING PROCESS TIMELINE — End-to-end loan lifecycle from application to repayment.**

Các mốc trên trục thời gian (xen kẽ trên/dưới):

- **D+0** — Nộp hồ sơ (KH nộp đơn vay + giấy tờ)
- **D+1~3** — Thẩm định hồ sơ (KYC, kiểm tra hồ sơ pháp lý)
- **D+4~7** — Đánh giá tín dụng (CIC, Credit Score, Xác minh thu nhập)
- **D+8~10** — Định giá TSĐB (Đánh giá tài sản bảo đảm + LTV)
- **D+11~12** — Phê duyệt (Hội đồng tín dụng ra quyết định)
- **D+13~14** — Giải ngân (Ký HĐ + chuyển tiền cho KH)
- **M+1~N** — Thu hồi nợ (Theo dõi kỳ trả, Thu lãi + gốc)

Hai giai đoạn lớn được đánh dấu bên dưới trục:

- ← **Pre-approval (D+0 → D+10)** →
- ← **Disbursement & Monitoring** →