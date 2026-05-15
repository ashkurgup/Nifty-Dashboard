import { Router, type IRouter } from "express";
import healthRouter from "./health";
import tradesRouter from "./trades";
import portfolioRouter from "./portfolio";

const router: IRouter = Router();

router.use(healthRouter);
router.use(tradesRouter);
router.use(portfolioRouter);

export default router;
