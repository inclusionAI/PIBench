import express from 'express'
import routeNames from '../config/alipayRoutes.config'
import * as alipayController from '../controllers/alipayController'

const routes = express.Router()

routes.route(routeNames.freeze).get(alipayController.freeze)
routes.route(routeNames.query).get(alipayController.query)
routes.route(routeNames.notify).post(alipayController.notify)

export default routes
