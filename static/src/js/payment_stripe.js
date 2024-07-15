/** @odoo-module **/

import { useService } from '@web/core/utils/hooks';
import { registry } from "@web/core/registry";
import { Component, EventBus ,useState , xml ,onWillStart} from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

//import {StripeTerminal} from
class PaymentStripe extends Component {
    setup() {
        this.orm = useService("orm");
        this.notificationService = useService("notification");
 
//        this.loadPaymentMethods();
        this.state = useState({
            discoveredReaders: [],
            connectedReader: null,
            connectionStatus: "not_connected",
            paymentStatus: null,
            paymentIntentId: null,
            transactionId: null,
            message: null,
            Json_discoveredReaders: null,
            amount: 0,
            selectedPaymentMethodId: null,
            paymentMethods: [],
            invoice_data : null,
            card_type:null,
            is_test:false,
            stripe_serial_number:'',
            hasConsent:false,
            payBtnDisabled:false,
            saveBtnDisabled:false,
            connectBtnDisabled:false,
            hasInterac:false,
            client_secret:false,
            cardPresentBrand:'',
        });
        this.createStripeTerminal();
    }
//    async onWillStart() {
////        await this.createStripeTerminal();
//     }
    async getStripeSerialNumber(){
    try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "get_stripe_serial_number",
                []
            );
            if (data.error) {
                throw data.error;
            }
            this.state.stripe_serial_number = data.stripe_serial_key;
            this.state.is_test = data.is_test;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }
    }
    async loadInvoiceAmount() {
        // Do not cache or hardcode the ConnectionToken.
        try {
            const data = await this.orm.silent.read(
                "account.move",
                [this.props.action.context.active_id],
                []
            );
            if (data.error) {
                throw data.error;
            }
            this.state.invoice_data = data
            this.state.amount = data[0].amount_residual
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }
    }
    async loadPaymentMethods(){
         // Do not cache or hardcode the ConnectionToken.
        try {
            await this.loadInvoiceAmount();
            const data = await this.orm.silent.call(
                "payment.provider",
                "get_partner_payment_ids",
                [[],this.state.invoice_data[0].partner_id[0]],

            );
            if (data.error) {
                throw data.error;
            }
            else if(data.not_found) {
                return false
            }
            this.state.paymentMethods = data.recs
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }
    }

    async confirm_intrec_txn(){
        try {
             const client_secret = this.state.client_secret;
             const data = await this.orm.silent.call(
                "payment.provider",
                "confirm_payment_intrec",
                [[],this.state.paymentIntentId,this.state.invoice_data],
             );
            if (data.error) {
                throw data.error;
            }
            this.state.message = data.status;
            this.state.hasInterac = false;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }

    }

     async update_txn_value(){
         try {
             const client_secret = this.state.client_secret;
             const data = await this.orm.silent.call(
                "payment.provider",
                "confirm_payment_intrec",
                [[],this.state.paymentIntentId,this.state.invoice_data,true],
             );
            if (data.error) {
                throw data.error;
            }
            this.state.message = data.status;
            this.state.hasInterac = false;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }

    }

    async stripeFetchConnectionToken() {
        // Do not cache or hardcode the ConnectionToken.
        try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "stripe_connection_token",
                []
            );
            if (data.error) {
                throw data.error;
            }
            return data.secret;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Token');
            this.terminal = false;
        }
    }

    async discoverReaders() {
        this.state.message = 'Discovering Reader...'
        const config = {};
        if (this.state.is_test == true){
            this.config = {simulated: true};
        };
        const discoverResult = await this.terminal.discoverReaders(this.config);
        if (discoverResult.error) {
            this._showError(_t("Failed to discover: %s", discoverResult.error));
        } else if (discoverResult.discoveredReaders.length === 0) {
            this._showError(_t("No available Stripe readers."));
        } else {
            // Need to stringify all Readers to avoid to put the array into a proxy Object not interpretable
            // for the Stripe SDK
            this.Json_discoveredReaders = JSON.stringify(discoverResult.discoveredReaders);
            this.state.message = 'Click on send to process the payment.';
            this.state.connectionStatus = 'Reader Found..'
        }
    }

    async checkReader() {
        try {
            if (!this.terminal) {
                const createStripeTerminal = this.createStripeTerminal();
                if (!createStripeTerminal) {
                    throw _t("Failed to load resource: net::ERR_INTERNET_DISCONNECTED.");
                }
            }
        } catch (error) {
            this._showError(error);
            return false;
        }
//        const line = this.pos.get_order().selected_paymentline;
        // Because the reader can only connect to one instance of the SDK at a time.
        // We need the disconnect this reader if we want to use another one
        if (
            this.connectedReader != this.state.stripe_serial_number &&
            this.terminal.getConnectionStatus() == "connected"
        ) {
            const disconnectResult = await this.terminal.disconnectReader();
            if (disconnectResult.error) {
                this._showError(disconnectResult.error.message, disconnectResult.error.code);
//                line.set_payment_status("retry");
                this.state.message = "retry";
                return false;
            } else {
                return await this.connectReader();
            }
        } else if (this.terminal.getConnectionStatus() == "not_connected") {
            return await this.connectReader();
        } else {
            return true;
        }
    }

    async connectReader() {
            this.state.connectBtnDisabled = true;
//        const line = this.pos.get_order().selected_paymentline;
        const discoveredReaders = JSON.parse(this.Json_discoveredReaders);
        for (const selectedReader of discoveredReaders) {
            if (selectedReader.serial_number == this.state.stripe_serial_number) {
                try {
                    const connectResult = await this.terminal.connectReader(selectedReader, {
                        fail_if_in_use: true,
                    });
                    if (connectResult.error) {
                        throw connectResult;
                    }
                    this.connectedReader = this.state.stripe_serial_number;
                    this.state.message = 'Reader Connected...!'
                    return true;
                } catch (error) {
                    if (error.error) {
                        this._showError(error.error.message, error.code);
                    } else {
                        this._showError(error);
                    }
//                    line.set_payment_status("retry");
                    this.state.message = "retry";
                    return false;
                }
            }
        }
        this._showError(
            _t(
                "Stripe readers %s not listed in your account",
                this.state.stripe_serial_number
            )
        );
    }

    _getCapturedCardAndTransactionId(processPayment) {
        const charges = processPayment.paymentIntent.charges;
        if (!charges) {
            return [false, false];
        }

        const intentCharge = charges.data[0];
        const processPaymentDetails = intentCharge.payment_method_details;
        if(processPaymentDetails.type === "card_present"){
             this.state.cardPresentBrand = processPaymentDetails.card_present.brand;
        }
        if (processPaymentDetails.type === "interac_present") {
            // Canadian interac payments should not be captured:
            // https://stripe.com/docs/terminal/payments/regional?integration-country=CA#create-a-paymentintent
            //show confirm button
            this.state.hasInterac = true;
            this.state.paymentIntentId = processPayment.paymentIntent.id
            return ["interac", intentCharge.id];
        } else if (this.state.cardPresentBrand.includes("eftpos")) {
            // Australian eftpos should not be captured:
            // https://stripe.com/docs/terminal/payments/regional?integration-country=AU
            return [this.state.cardPresentBrand, intentCharge.id];
        }

        return [false, false];
    }

    async collectPayment(amount) {
        // This is test visa debit card , it can be updated to your test card!
        this.terminal.setSimulatorConfiguration({testCardNumber: '4000056655665556'});
//        const line = this.pos.get_order().selected_paymentline;
        const clientSecret = await this.fetchPaymentIntentClientSecret(amount);
        if (!clientSecret) {
            this.state.message = "retry";
            this.state.payBtnDisabled = false;
            this.state.saveBtnDisabled = false;
            return false;
        }
        this.state.message = "waitingCard";
        const collectPaymentMethod = await this.terminal.collectPaymentMethod(clientSecret,{enable_customer_cancellation: true});
        if (collectPaymentMethod.error) {
            this._showError(collectPaymentMethod.error.message, collectPaymentMethod.error.code);
//            line.set_payment_status("retry");
            this.state.message = "retry";
            this.state.payBtnDisabled = false;
            this.state.saveBtnDisabled = false;
            return false;
        } else {
            this.state.message = "waitingCapture";
            const processPayment = await this.terminal.processPayment(
                collectPaymentMethod.paymentIntent,
                {"enable_customer_cancellation": true}
            );
            this.state.transactionId = collectPaymentMethod.paymentIntent.id;
            if (processPayment.error) {
                this._showError(processPayment.error.message, processPayment.error.code);
                this.state.message = "retry";
                this.state.payBtnDisabled = false;
                this.state.saveBtnDisabled = false;
                return false;
            } else if (processPayment.paymentIntent) {
                this.state.message = "waitingCapture";
                const [captured_card_type, captured_transaction_id] = this._getCapturedCardAndTransactionId(processPayment);
                if (captured_card_type && captured_transaction_id) {
                    this.state.card_type = captured_card_type;
                    this.state.transaction_id = captured_transaction_id;
                } else {
                    await this.captureAfterPayment(processPayment);
                }
                this.state.message = "done";
                this.state.payBtnDisabled = false;
                this.state.saveBtnDisabled = false;
                return true;
            }
        }
    }


     stripeUnexpectedDisconnect() {
        // Include a way to attempt to reconnect to a reader ?
        this.state.connectBtnDisabled = false;
        this._showError(_t("Reader disconnected"));
        }
    async createStripeTerminal() {
        try {
            await this.getStripeSerialNumber();
            await this.loadPaymentMethods();
            this.terminal = StripeTerminal.create({
                onFetchConnectionToken: this.stripeFetchConnectionToken.bind(this),
                onUnexpectedReaderDisconnect: this.stripeUnexpectedDisconnect.bind(this),
            });
            this.discoverReaders();
            return true;
        } catch (error) {
            this._showError(_t("Failed to load resource: net::ERR_INTERNET_DISCONNECTED."), error);
            this.terminal = false;
            return false;
        }
    }

    async captureAfterPayment(processPayment) {
        const capturePayment = await this.capturePayment(processPayment.paymentIntent.id);
        if (capturePayment.charges) {
            this.state.card_type =
                capturePayment.charges.data[0].payment_method_details.card_present.brand;
        }
        this.state.transactionId = capturePayment.id;
    }

    async capturePayment(paymentIntentId,confirm=false,token=false) {
        try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "stripe_capture_payment",
                [paymentIntentId,this.state.invoice_data,confirm,token]
            );
            if (data.error) {
                throw data.error;
            }
            return data;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Capture Payment');
            return false;
        }
    }

    async fetchPaymentIntentClientSecret(amount) {
        try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "stripe_payment_intent",
                [[],amount,this.state.invoice_data],

            );
            if (data.error) {
                throw data.error;
            }
            this.state.client_secret = data.client_secret;
            return data.client_secret;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Secret');
            return false;
        }
    }

     async fetchSetupIntentClientSecret() {
        try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "stripe_ter_setup_intent",
                [[],this.state.invoice_data],

            );
            if (data.error) {
                throw data.error;
            }
	     return data;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Secret');
            return false;
        }
    }

    async tokenCollectPayment(amount){
        try {
            const data = await this.orm.silent.call(
                "payment.provider",
                "stripe_payment_intent",
                [[],amount,this.state.invoice_data,this.state.selectedPaymentMethodId],

            );
            if (data.error) {
                throw data.error;
            }
            return data;
        } catch (error) {
            const message = error.code === 200 ? error.data.message : error.message;
            this._showError(message, 'Fetch Secret');
            return false;
        }
    }
    async send_payment_request() {
        /**
         * Override
         */
//        await super.send_payment_request(...arguments);
//        const line = this.pos.get_order().selected_paymentline;
        this.state.message = "waiting"
        this.state.payBtnDisabled = true;
          try {
            if (this.state.amount > this.state.invoice_data[0].amount_residual){
                this._showError("Amount Cannot be Greater than the Invoice Amount!");
                this.state.payBtnDisabled = false;
                return false
            }
            if (this.state.selectedPaymentMethodId){
                const tokenPaymentIntent = await this.tokenCollectPayment(this.state.amount)
                if(tokenPaymentIntent.error)
                {
//                Show Error
                }
                else{
//                    Show a confirmation message to deduct the payment
//                    Confirm the payment
                    const confirm = await this.capturePayment(tokenPaymentIntent.id,true,this.state.selectedPaymentMethodId)
                    if (confirm.error){
//                        Display the Error
                    }
                    else{
//                    Display Done
                    this.state.message = 'Transaction Successfully Completed !'
                        return true
                    }

                }
            }
            if (await this.checkReader()) {
                return await this.collectPayment(this.state.amount);
            }
        } catch (error) {
            this._showError(error);
            return false;
        }
    }


    async stripeCancel() {
        if (!this.terminal) {
            return true;
        } else if (this.terminal.getConnectionStatus() != "connected") {
            this._showError(_t("Payment canceled because not reader connected"));
            return true;
        } else {
            const cancelCollectPaymentMethod = await this.terminal.cancelCollectPaymentMethod();
            if (cancelCollectPaymentMethod.error) {
                this._showError(
                    cancelCollectPaymentMethod.error.message,
                    cancelCollectPaymentMethod.error.code
                );
            }
            return true;
        }
    }

    async send_payment_cancel(order, cid) {
        /**
         * Override
         */
//        super.send_payment_cancel(...arguments);
//        const line = this.pos.get_order().selected_paymentline;
        const stripeCancel = await this.stripeCancel();
        if (stripeCancel) {
//            line.set_payment_status("retry");
            this.state.message = "retry"
            return true;
        }
    }


    // private methods
    _showError(msg, title) {
//       this.notificationService.add(msg,{title:title,type:'danger'});
        this.state.message = msg
    }
}
PaymentStripe.template = "stripe_account_move.StripePayment";

//PaymentStripe.props = {
//    stripeSerialNumber: String,
//};
registry.category("actions").add('payment_stripe', PaymentStripe);
export default PaymentStripe;
