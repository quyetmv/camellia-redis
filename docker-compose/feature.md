# Phân chia ngắn gọn cho AI Agent: Camellia Redis Proxy Config Platform

## Mục tiêu

Xây hệ thống quản lý config cho Camellia Redis Proxy, lưu runtime config vào etcd, có frontend và API để tạo draft, validate, publish, rollback và audit.[1][2]

## Agent 1: Product/BA

- Chốt scope MVP.
- Viết user story và acceptance criteria.
- Chốt workflow: draft -> validate -> approve -> publish -> rollback.
- Chốt vai trò: admin, operator, auditor.

## Agent 2: Solution Architect

- Thiết kế kiến trúc tổng thể.
- Chốt ranh giới giữa metadata DB và runtime config trên etcd.
- Thiết kế etcd key convention.
- Chốt model versioning và rollback.[2]

## Agent 3: Backend API

- Build CRUD draft config.
- Build API validate config.
- Build API versioning, publish, rollback.
- Build audit log API.
- Tích hợp etcd client để ghi active config.[2]

## Agent 4: Validator Engine

- Kiểm tra schema config.
- Kiểm tra rule vận hành trước publish.
- Trả lỗi/warning theo field.
- Chặn publish nếu validate fail.

## Agent 5: Frontend

- Build màn hình Dashboard.
- Build Config List + Config Editor.
- Build Validation View.
- Build Diff + Publish screen.
- Build Audit Log screen.

## Agent 6: DevOps/SRE

- Dựng PostgreSQL, etcd, API, frontend.
- Thiết kế CI/CD.
- Thiết lập logging, metrics, alert.
- Kiểm tra publish thật vào môi trường test.
- Xác minh Camellia đọc config từ source tương ứng.[1][3]

## Agent 7: QA

- Viết test case cho draft/validate/publish/rollback.
- Test permission theo role.
- Test lỗi khi etcd unavailable.
- Test rollback và audit trail.

## Output mong muốn

- Frontend nội bộ để quản lý config.
- Backend API hoàn chỉnh.
- Runtime config lưu trong etcd.
- Có version, rollback, audit.
- Có tài liệu bàn giao ngắn gọn.

## Ưu tiên thực hiện

1. BA + Architect chốt scope và key design.
2. Backend + Validator build API và publish flow.
3. Frontend build màn hình quản trị.
4. DevOps dựng môi trường test tích hợp.
5. QA test end-to-end.